# Brief: thinking-budget forcing for the local capped-thinking lane

## task
Implement s1-style **thinking-budget forcing** for the `capped-thinking` lane when the provider
is `local` (an OpenAI-compatible local server such as vLLM). Work in the repository at
`C:\Users\Michael\local-bench` (cd there first). Branch `suite/v1-quant-wedge`. **Commit locally;
DO NOT push.** No network/GPU is needed — all tests use mocked transports.

### Why (verified live, do not re-litigate)
Reasoning-on (`capped-thinking`) on local vLLM served with `--reasoning-parser qwen3`: small Qwen3
models keep thinking past the `max_tokens` cap (16384) **without ever emitting `</think>`**. The
qwen3 reasoning parser buffers chain-of-thought and only flushes `reasoning_content` when it sees
the closing `</think>`. Truncated before that, vLLM returns **empty `content` AND empty
`reasoning_content`** → empty `response_text` → scored wrong (no answer). Measured: ~65% of items
on Qwen3.5-4B. This makes the headline lane unusable for small local reasoning models and confounds
discrimination (models floor on non-termination, not on knowledge).

### The fix (verified working live against this vLLM)
Two-pass budget forcing on the **raw `/v1/completions`** endpoint (the chat endpoint loses the text
on truncation; raw completions does not, because no reasoning parser is in the path):
- **Pass 1 (think):** render the chat messages to a raw ChatML prompt ending at the assistant turn;
  POST `{base}/completions` with `max_tokens=think_budget`, `stop=["</think>"]`, temperature from
  decoding. Capture the raw text (the thinking) and `finish_reason`.
  - `finish_reason == "stop"` → the model closed `</think>` within budget (NOT forced).
  - `finish_reason == "length"` → budget exceeded (forced-close).
- **Pass 2 (answer):** `prompt = pass1_prompt + pass1_text + "\n</think>\n\n"`; POST
  `{base}/completions` with `max_tokens=answer_budget`, `stop=["<|im_end|>"]`. Capture the answer.
- Pass 2 ALWAYS runs (with `stop=["</think>"]`, pass 1 halts before the answer is generated).

Verified ChatML format (single user message):
`<|im_start|>user\n{content}<|im_end|>\n<|im_start|>assistant\n` — the model itself emits
`<think>\n...`. The renderer must NOT inject `<think>` and must NOT add any enable_thinking
sentinel.

## completeness_contract
1. **New module `cli/src/localbench/budget_forcing.py`:**
   - `render_qwen3_chat_prompt(messages: list[ChatMessage]) -> str` — render system/user/assistant
     roles into Qwen3 ChatML, ending with `<|im_start|>assistant\n` (add_generation_prompt).
     Targets the Qwen3 family (the only family budget-forcing supports today); name/doc it as such.
   - `async def run_forced_completion(*, client, base_url, model, messages, decoding, think_budget,
     answer_budget) -> ParsedCompletion` — the two-pass logic above. `base_url` is the API base
     (e.g. `http://127.0.0.1:8000/v1`); POST to `f"{base_url}/completions"`. temperature from
     `decoding` (default 0); forward `seed`/`top_p` etc. from decoding where present, but NEVER
     forward `max_tokens`/`chat_template_kwargs`/`thinking_budget` into the completions body (set
     `max_tokens` explicitly per pass). Returns `ParsedCompletion` with:
       - `response_text` = pass-2 answer text (strip a trailing `<|im_end|>` / whitespace),
       - `reasoning_text` = pass-1 thinking text,
       - `finish_reason` = `"stop"` when pass 2 produced a complete answer (pass-2 finish == stop),
         else `"length"` (the ANSWER itself was truncated),
       - `usage` = element-wise sum of pass-1 + pass-2 usage (prompt/completion/total tokens),
       - force-close recorded (see #2).
2. **Record force-close transparently.** Add an optional field (default `False`) `thinking_forced`
   to `ParsedCompletion` (`cli/src/localbench/_types.py`) and carry it into `ItemResult`
   (`_requests.py::item_result`). Requirements: (a) `lane_conformance.py` must continue to treat a
   forced-but-answered item as **headline-comparable** — it has a non-empty `response_text` and
   `finish_reason == "stop"`, so the existing truncation / no-final-answer logic already passes it;
   do not regress that. (b) The run can aggregate `thinking_forced` to report a force-close rate.
   Update every `ParsedCompletion`/`ItemResult` constructor + TypedDict + any test that asserts exact
   keys. Safe default everywhere so existing providers (anthropic/openai/gemini) are unchanged.
3. **Integrate in `_requests.py::run_item`.** Add param `base_url: str | None = None`. Route to
   `run_forced_completion` ONLY when `provider.name == "local"` AND `lane == "capped-thinking"` AND
   the item carries an int `think_budget` AND `base_url` is set. Wrap it in the SAME retry / timing /
   error handling as the normal path (it may raise `httpx.TransportError`, `ResponseParseError`,
   `ProviderPayloadError`). Otherwise use the existing single-pass path UNCHANGED. Thread `base_url`
   from `runner.run_benchmark` (it already computes `endpoint`).
4. **Plumb `think_budget` in `orchestrate.py`.** For `provider == "local"` and
   `lane == "capped-thinking"`, read the per-bench budget from suite.json bench config
   `lane_caps["capped-thinking"]["think_budget"]` if present, else a module-level methodology
   constant `CAPPED_THINKING_THINK_BUDGET = 8192` (document it as the locked methodology budget). Set
   `benchmark_item["think_budget"] = think_budget`. Keep the item's existing `max_tokens` as the
   total ceiling. `answer_budget = max(total_cap - think_budget, 1024)`. Add `think_budget` to the
   `BenchmarkItem` TypedDict as `NotRequired[int]`.
5. **Fix `manifest.py`.** `_caps` hardcodes `"thinking_budget": 0`. Record the actual budget for the
   capped-thinking lane (from the bench/sampling config or items); keep 0/absent for lanes without
   forcing. Update manifest tests.
6. **Populate `suite/v1/suite.json` `lane_caps`** for `mmlu_pro` and `ifbench` (at minimum) with
   `{"capped-thinking": {"think_budget": 8192}}`. CRITICAL: suite.json feeds a drift / scorecard /
   itemset-hash gate. Confirm adding `lane_caps` does NOT change item-set sha256s or break the suite
   drift gate / scorecard-identity tests. If it does, STOP and surface it in your summary rather than
   weakening the gate.

## verification_loop
- Add unit tests (cli/tests) covering: `render_qwen3_chat_prompt`; `run_forced_completion` via a
  mocked httpx transport for (a) pass1 length → forced → pass2 stop answer, (b) pass1 stop → not
  forced → pass2 answer, (c) pass2 length → `finish_reason == "length"`, (d) usage summed; `run_item`
  routing (local+capped-thinking+think_budget → forcing; every other lane/provider → unchanged
  single-pass); `lane_conformance` classifies a forced-but-answered item as headline-comparable;
  manifest records the budget.
- Run the FULL suite: `cd cli && .venv\Scripts\python.exe -m pytest tests -q` — must stay green
  (currently 603). Run ruff/lint if configured. Make NO network calls.

## action_safety
Stay within `cli/` + `suite/v1/suite.json` + (if needed) `docs/`. Do NOT refactor unrelated code,
do NOT change the answer-only / api-uncapped lanes or the anthropic/openai/gemini providers, do NOT
push, do NOT alter item-set files or hashes. Keep the diff focused and additive. Preserve existing
public signatures except the additive `base_url` param and the optional `thinking_forced` field.

## output
End with a concise summary: files changed; the force-close metadata mechanism; test count
before/after; and any drift-gate / schema concerns surfaced.

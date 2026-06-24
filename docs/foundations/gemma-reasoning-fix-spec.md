# Gemma-4 reasoning activation + reasoning-format registry (oracle-reviewed spec)

Date 2026-06-23. Source: GPT-5.5 Pro (oracle) `gemma-reasoning-activation-methodology-review`
(full transcript in that session), weighed against the CLI agent's own analysis + code read.

## Trigger / incident
gemma-4-31B was benchmarked **answer-only** (~66-67) because a `<think>`-shaped probe missed
gemma's `<|channel>thought…<channel|>` format and our harness had no gemma activation. Qwen ran
capped-thinking, gemma did not → the comparison + the gemma numbers are a **lane-conformance
incident**, not a small bug. Existing gemma numbers = diagnostic answer-only FLOOR, superseded
for headline ranking.

## Two corrections the consult surfaced
1. **gemma turn-stop = `<turn|>`, NOT `<end_of_turn>`** (Google Gemma-4 prompt-formatting docs +
   HF tokenizer_config `eot_token`). Format is `<|channel>thought\n…<channel|>final answer<turn|>`.
2. **Latent footgun (VERIFIED not to affect our data):** `answer_budget_for` defaults to a 4096
   answer budget when `max_tokens` is missing. Our items carry `max_tokens=16384` → ran true
   8192/8192. FIX anyway: fail-closed (missing `max_tokens` on a ranked capped-thinking run = a
   config error, not a silent 4096).

## Correct gemma-4 forcing grammar
```
activation         = chat_template_kwargs {"enable_thinking": True}   (or <|think|> control token)
reasoning_open     = "<|channel>thought\n"
reasoning_close    = "<channel|>"
forced_reasoning_close = "\n<channel|>"
answer_stop        = ["<turn|>"]
answer_reparse_regex = (?s)<\|channel>thought\n(.*?)<channel\|>
```
Force-close is probably clean (answer follows directly after `<channel|>`, no separate
answer-channel token) — but VALIDATE empirically (forced close → nonempty answer, no loops/leaks).
Also check **double-BOS** (gemma template emits `<bos>`; ensure llama-server `/completions` does
not add a second).

## Build it as a REGISTRY, not just parameterized delimiters
Don't stop at open/close/answer-stop. A ranked reasoning entry must parameterize + HASH:
activation method, HF tokenizer/processor **revision (commit, not `main`)**, chat_template sha256,
rendered-prompt hash, forced-close string, answer-stop seqs, stop-string-return behavior,
answer-pass re-reasoning scrubber, leak regexes, multi-turn thought-stripping, validation
fixtures, registry version. Target shape:
```python
@dataclass(frozen=True)
class ReasoningRegistryEntry:
    id; version; status: Literal["ranked","diagnostic","experimental"]; model_match
    renderer; activation; forcing; parser; conformance; provenance
```
`budget_forcing.py` should receive a resolved `ReasoningRegistryEntry`, not a loose
`PromptRenderer`. **Registry changes are scorecard changes** → new scorecard/runtime id.

## Fairness policy (ranked capped-thinking)
Use ONLY documented-native activation: official chat-template kwarg / control token / model-card
instruction / official server-parser. Native: gemma `enable_thinking`, Qwen `<think>`, granite
`thinking:True` (if official). **FLAG: our nemotron "detailed thinking on" hand-written system
message is NON-native → mark diagnostic/experimental, NOT equal-ranked.** Separate identities:
task-suite / scorecard / lane / model-operating-mode / activation.

## Hybrid models (best-native-mode leaderboard)
Do **NOT** rank by `max(answer_only, capped_thinking)` on the same eval set (free extra shot /
eval-set mode selection). Policy: **headline = capped-thinking; thinking-capable model → run
thinking-ON (option b); no-thinking model → native chat, labeled `reasoning_capability: none`.**
Answer-only for a thinking-capable model = secondary cost/latency view, not headline.
max-of-two only if the mode is chosen on a pre-registered held-out calibration split.

## Re-run scope (staged)
- Stage 1: gemma **Q4 capped-thinking smoke + validation** (the checklist below).
- Stage 2: full gemma **Q4 standard run** = the corrected public gemma-thinking number.
- Stage 3: full **Q3/Q4/Q5/Q6 ladder** ONLY if we keep a gemma quant-ladder/plateau claim.
**CORRECTION: the gemma "Q4 plateau / flat to Q3" finding does NOT survive** — it was answer-only,
and reasoning-ON can change token count, cap-hit, churn, and quant sensitivity. Until re-run, the
gemma quant-ladder claim is UNVERIFIED; mark the old ladder answer-only-diagnostic/superseded.

## Validation gates BEFORE publishing gemma-thinking numbers
- **Static render tests:** contains `<|think|>` when enabled; ends at `<|turn>model\n`; no
  pre-closed empty thought channel in thinking-on; uses `<|turn>`/`<turn|>` (not old gemma
  tokens); exactly one BOS; stable sha256 fixture.
- **Dynamic smoke (10-20 prompts, large cap):** output contains `<|channel>thought\n` then
  `<channel|>`; nonempty final answer after; stops on `<turn|>`; scored answer has NO
  `<|channel>`/`<channel|>`/`<|think|>`/`<turn|>`.
- **Forced-close (budgets 32/128/512):** pass-1 `finish_reason=length` on some; pass-2 still emits
  an answer; no leaked tags; no systematic blank; no repeated thought blocks.
- **Negative control (`enable_thinking=False`):** materially different — measure **nonempty
  thought BODY**, not tag presence (some gemma sizes emit an empty thought channel even off).
- **30-50 item conformance slice:** parse_success 100%; nonempty_final_answer ~100% (excl. true
  cap-fails); leaked_reasoning 0%; special-token-leak 0%; answer_cap_hit visible+audited;
  forced_close_success high. Any cap-hit scored CORRECT → manual audit.

## Implementation corrections (concrete)
1. `ReasoningActivation += "gemma4"`; `_chat_template_kwargs("gemma4") -> {"enable_thinking": True}`
   — then migrate to the registry (nemotron-system vs gemma-kwarg are different activation classes).
2. Replace hardcoded Qwen forcing with a `ForcingFormat` object (Qwen `</think>`/`<|im_end|>`;
   gemma `<channel|>`/`<turn|>`).
3. `answer_budget_for`: fail-closed on missing/non-int `max_tokens` for ranked runs.
4. Re-label existing gemma answer-only numbers (site + docs): diagnostic floor, not headline,
   not comparable to Qwen capped-thinking.
5. Pin gemma HF tokenizer revision (commit) + chat_template hash; do NOT use `main` unpinned.

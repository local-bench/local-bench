# Spec: wire reasoning activation through the bench path, fail-closed (2026-07-02)

Unblocks the capped-thinking canary (plan `docs/deploy/plan-ranked-row-2026-07-02.md`).
All findings below were verified against code and run artifacts on 2026-07-02. `cli/` only.

## Root cause (verified)

The 2026-07-02 mini-run (`runs/bench/minirun-leakfix-4axis-2026-07-02/`, capped-thinking,
Gemma-4-12B) scored ifbench 10% vs the pilot's 0.687. Diagnosis chain:

- Local capped-thinking is enforced CLIENT-side by two-pass budget forcing on the raw
  `/v1/completions` endpoint (`budget_forcing.run_forced_item`) — server `--reasoning-*`
  flags are inert on that endpoint (no template application, no reasoning parser).
- Routing engaged correctly (raw results show `thinking_forced` + summed two-pass usage),
  BUT with the WRONG family machinery:
  - `bench` exposes no `--reasoning-activation` / `--hf-model-id` (parser at `cli.py:244-273`),
    and `serving/bench.py:build_orchestrate_config` never sets them, so
    `OrchestrateConfig.reasoning_activation` silently defaulted to **"qwen3"**
    (`orchestrate.py:182`) and `hf_model_id=None`.
  - `orchestrate.py:346` therefore selected `qwen_thinking_native_v1` (the mini-run manifest
    honestly records it at `manifest.sampling.reasoning_registry_entry_id`), giving
    QWEN_FORCING: pass-1 stop `</think>` (Gemma never emits it → every long thought runs to
    the hard 8192 cap), forced close `\n</think>\n\n` (meaningless to Gemma), answer stop
    `<|im_end|>` (never emitted).
  - `hf_model_id=None` → `build_forced_prompt_renderer` returns None
    (`prompt_rendering.py:74-75`) → `render_qwen3_chat_prompt` rendered Gemma's prompts as
    **Qwen ChatML**. Evidence: raw results show the model emitting its own
    `<|channel>thought\n` scaffold at position 0 and blowing through it.
- The June-30 pilot got 0.687 because the `run` path passed
  `--reasoning-activation gemma4 --hf-model-id unsloth/gemma-4-12b-it` → registry entry
  `gemma4_thinking_native_v1` + HF chat-template renderer (`enable_thinking=True`) +
  GEMMA4_FORCING (pass-1 stop `<channel|>`, answer stop `<turn|>`). Its manifest records
  exactly that.
- Supporting facts: mini-run manifest `model.family == "gemma4"` (from GGUF metadata);
  gemma4 entry `model_match = ("unsloth/gemma-4-31B-it", "gemma-4", "gemma4")`;
  `unsloth/gemma-4-12b-it` is present in the offline HF cache on this box.

So this is a wiring gap plus a missing fail-closed guard: a publishable orchestrated run
silently used another family's forcing machinery and stayed "green".

## Work item 1 — bench CLI flags + plumbing

1. Add to the `bench` parser (`cli.py:244-273`):
   - `--reasoning-activation` with `choices=REASONING_ACTIVATIONS` (import from
     `prompt_rendering`), default None.
   - `--hf-model-id` (str, default None).
2. Validation in `_bench` (before launch): if `--lane capped-thinking`, BOTH flags are
   REQUIRED — exit with a clear usage error naming the missing flag(s) (use the existing
   usage-error path/exit code that `_bench` uses for bad input; do not launch the server
   first). For `--lane answer-only` (and `api-uncapped`), REJECT either flag if provided
   (strict, consistent with the fail-closed argv posture): clear usage error.
3. `BenchRunConfig` (`serving/bench.py`) gains `reasoning_activation` and `hf_model_id`
   fields; `build_orchestrate_config` forwards both into `OrchestrateConfig` (which already
   has the fields, `orchestrate.py:181-182`).
4. Ensure both values land in the recorded campaign config / manifest the same way the
   `run` path records them (the run path records `model.hf_model_id`; additive fields only).

## Work item 2 — fail-closed guards in orchestrate (publishable runs)

In the local capped-thinking block (`orchestrate.py:341-351`), when `config.publishable`
is True and `thinking_budget > 0`:

1. `reasoning_entry_for_activation(config.reasoning_activation)` returning None →
   RuntimeError naming the activation ("no ranked reasoning-registry entry"). Today
   granite/nemotron/r1 fall through to `run_forced_item`'s implicit QWEN default — the
   same silent-mismatch class as this bug.
2. Family match: when `config.model_family` is a non-empty string, require it to match at
   least one of `entry.model_match` patterns (case-insensitive `fnmatch`; treat plain
   entries as exact matches). Mismatch → RuntimeError naming family, activation, entry id,
   and the patterns. When `model_family` is None (bare run path), skip this check.
3. Renderer: `config.hf_model_id` None → RuntimeError ("publishable capped-thinking
   requires --hf-model-id; the ChatML fallback renderer is only valid for diagnostic
   runs"). This bans `render_qwen3_chat_prompt` from publishable runs for ALL families —
   qwen included (its HF template is ChatML anyway, so behavior is preserved, but rendered
   through the model's own template).

Non-publishable runs keep today's behavior (back-compat for diagnostic/dev runs).
Do NOT change `run_benchmark`/`run_item` defaults in `runner.py`/`_requests.py` — the
orchestrate-level guard is the integrity boundary; runner defaults are run-path compat.

## Work item 3 — tests

- bench parser: capped-thinking without either flag → usage error (both named);
  answer-only with either flag → usage error; capped-thinking with both → values appear on
  `BenchRunConfig` and `OrchestrateConfig` (unit-test `build_orchestrate_config`).
- Guards: publishable + capped + activation qwen3 + model_family "gemma4" → RuntimeError;
  publishable + capped + activation gemma4 + model_family "gemma4" + hf_model_id set →
  passes the guard block; publishable + capped + hf_model_id None → RuntimeError;
  publishable + capped + activation granite → RuntimeError (no entry);
  non-publishable + capped + defaults → no raise (back-compat).
- Existing suite green.

## Explicitly out of scope / unchanged

- Server argv for capped-thinking stays exactly as committed (`--reasoning on
  --reasoning-budget 8192 --reasoning-format deepseek`): inert for forced raw-completions
  items, correct for any chat-endpoint traffic, and the pinned identity already recorded it.
- `validate_capped_thinking_context` stays as-is (its bound is conservative for the
  two-pass shape: pass-2 context need = prompt + think + answer_budget ≈ prompt +
  max_tokens ≤ its required minimum).
- No changes to `budget_forcing.py`, the reasoning registry, scorecard identity, or any
  released SCORECARD.json.

## Hard constraints

- `cli/` only. `cli/runs/board/board_v1.json` untouched (git blob `3d058e60…`).
- Additive manifest/campaign fields only (result_bundle contract is live).
- Full pytest suite green (baseline 1010 passed / 13 skipped / 1 xfailed).
- No GPU runs, no push, no deploy, no commit.

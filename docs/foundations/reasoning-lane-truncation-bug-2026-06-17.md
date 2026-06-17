# Reasoning-lane truncation bug + graceful-budget fix (2026-06-17)

*A core validity bug in the `capped-thinking` lane, found while measuring calibration throughput. The lane's
hard `max_tokens` cap was truncating verbose reasoning mid-thought and scoring the truncation as a wrong answer.
The fix (a graceful server-side reasoning budget) is both **more honest** and **2-5x faster** — the two goals
converge.*

## The bug
The `capped-thinking` lane applied a hard per-axis `max_tokens` cap (knowledge = 12288). Verbose reasoning models
routinely exceed it and get **cut off before committing an answer** → no parseable answer → scored WRONG. The
lane was measuring the cap, not the model.

Evidence (mmlu_pro):
- **Gemma-4-12B:** 21 of 24 items hit `finish_reason=length` (median completion = 12288); **all 16 wrong answers
  were truncated** — zero clean-finished answers were wrong.
- **Qwen-3.6-27B-Q6** (wedge ladder): 14/40 truncated; 12 of 16 wrong were truncations.
- **Qwen-3.6-27B-Q2:** 11/40 truncated; 9 of 11 wrong were truncations.

So ~70-100% of "knowledge errors" across models were truncation casualties, not real mistakes. This is the same
truncation failure mode that produced the earlier math-FP artifact — here hiding inside the reasoning lane. It
also **cleanly explains the earlier "answer-only scored higher than reasoning" signal** (answer-only doesn't
truncate) that had been shelved as contamination — the direction was real.

## The fix: graceful reasoning budget, not a hard cap
Serve with llama.cpp `--reasoning-budget N` — the model gracefully ENDS its thinking at N tokens and commits an
answer, instead of being truncated mid-thought. Measured on the 27B (mmlu_pro, n=32):

| budget | accuracy | truncated | median tok |
|---|---|---|---|
| unbounded (hard 12288 cap) | ~60% | high | ~12k (truncates) |
| graceful 4096 | 84.4% | 1/32 | 4,551 |
| graceful 8192 | **93.8%** | 2/32 | 8,324 |

Gemma-4-12B: 33% (unbounded) → 75% (graceful 4096). Accuracy is monotonic in the graceful budget; the models use
the reasoning productively.

## Decision
**Lane reasoning-budget = 8192** (operating point): 93.8% on the 27B, mostly graceful (2/32 still want more), a
+34pt recovery over the truncating cap, and tractable. Serving change: pass `--reasoning-budget 8192`; keep the
localbench `max_tokens` as a safety ceiling ABOVE the budget.
- **Caveat:** accuracy was still climbing 4096→8192, so 8192 may slightly under-measure the most verbose models.
  For difficulty **binning** (the calibration's job) this is fine — relative item difficulty ordering is stable.
  Before publishing **absolute** scores, check a graceful ~10-12k budget to confirm 8192 isn't under-measuring.
- **Per-axis:** knowledge needs the most; the 8192-cap axes (ifbench/bfcl/lcb) reason less, so a uniform 8192
  graceful budget is a safe start; per-axis budgets are a later refinement. Math is floored (frontier-only).

## Implications (must action)
1. **Prior absolute knowledge numbers are truncation-depressed** — the wedge ladder and likely the anchors were
   run at the hard cap. Re-measure at budget 8192.
2. **The quant wedge partly survives** (both quants truncated similarly → the paired delta largely cancels, which
   is part of why it read ~flat) but must be **re-measured cleanly** at the graceful budget.
3. **Lane spec change:** `reasoning-lane-spec` moves from hard `max_tokens` cap → graceful `--reasoning-budget`.
4. **Product CLI:** users' backends differ — llama.cpp uses `--reasoning-budget`; vLLM/Ollama differ. The CLI must
   apply/verify a graceful budget per backend, or results silently truncate. (Adds to the launch-readiness list.)

## Speed bonus
The fix also cuts tokens/item (~12k truncating → ~8k graceful) and avoids truncation re-tries, so it is ~2-5x
faster — which is what surfaced it (the calibration was 4x slower than estimated because models rambled to ~12k).

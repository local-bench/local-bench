# Site data contract — strict scoring + IFBench decomposition (2026-06-21, RECONCILED)

**Updated after inspecting the campaign scorer (`cli/src/localbench/_scoring.py`) — this supersedes
the original nested-block proposal.** Reconciliation method: no direct agent-to-agent channel exists,
so the SITE conforms to the PRODUCER's actual output (read their code, lane-safe). The producer emits
the decomposition **flat on each bench/axis aggregate**, not in a nested block.

## Lane rule (unchanged)
- `cli/` owns scoring; `web/` consumes + validates + renders. Web never computes strict from per-item
  `finish_reason`, nor derives the LII composite/axes — it trusts the pipeline's `composite`/`axes`.

## Actual emitted shape — `cli/_scoring.py` `BenchAggregate` (per bench)
- `raw_accuracy` — **IS the strict accuracy** (the strict re-score already counts non-terminating
  answers as incorrect).
- `chance_corrected` — the corrected score that feeds the axis point + composite.
- `termination_rate` = `n_terminated / n`  (terminated = `finish_reason != "length"`).
- `conditional_accuracy` = `n_correct / n_terminated`.
- `n`, `n_extraction_failures`, `n_errors`.
- Identity: `raw_accuracy (strict) = termination_rate × conditional_accuracy` (raw proportions).

## What the site reads (per axis, after `build_data`)
- `axis.raw_accuracy` = strict raw accuracy (already surfaced).
- `axis.termination_rate`, `axis.conditional_accuracy` — **OPTIONAL**; present once the run JSONs are
  re-emitted by the strict scorer. Absent on legacy / scoreless data → the site renders **"pending"**.
- Presence = final (the strict scorer is the only scorer now); no separate `status` field is emitted.

## Plumbing needed (web/, my lane — small, tolerant)
1. `build_data_axes.py._axis_from_benches` currently keeps `{point/lo/hi, n, n_errors, n_no_answer,
   raw_accuracy}` and **drops** `termination_rate`/`conditional_accuracy`. Add a weighted pass-through
   of those two fields **tolerant of absence** (skip when a source bench lacks them, so legacy run
   JSONs still build).
2. web `AxisScore` zod schema: add optional `termination_rate` + `conditional_accuracy`.

## Handoff — what the campaign agent must do (their lane)
- Re-emit the campaign run JSONs with the **current** strict scorer, so each bench aggregate carries
  `termination_rate` + `conditional_accuracy` + strict `raw_accuracy`; then wire via
  `data_sources.json` → rebuild `public/data`. The numbers are already official (the RESULT doc); the
  only gap is machine-readable re-emission.
- **No new field names to invent — they already exist in `cli/_scoring.py`.** ✅ Reconciled.

## Method note the site will show
> "Outputs that hit the answer-token cap are counted incorrect; this prevents non-terminating
> generations from getting credit for matching required tokens inside a runaway response."

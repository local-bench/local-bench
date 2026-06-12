<task>
GOAL (architecture): make scoring ONE consistent estimand across the CLI and the web pipeline.
Today the CLI stores a CLAMPED chance-corrected score while the web pipeline computes UNCLAMPED
bootstrap CIs with a single artificial stratum and drops errored items — three divergences that
make the displayed point and interval describe different things. Fix all three at the root.
This is on branch `refactor/architecture`. Fixes code-review findings #1, #2, #3
(docs/code-review-findings.md). Do NOT re-run benchmarks; reuse existing run JSONs.

1. UNCLAMP stored chance-corrected — cli/src/localbench/_scoring.py:
   - `aggregate()` currently returns `"chance_corrected": max(0.0, corrected)`. Store the UNCLAMPED
     signed value instead (reuse `localbench.scoring.signed_score.signed_score(raw_accuracy, chance=baseline)`
     so there is ONE definition; it may be negative for below-chance). `composite()` must sum the
     UNCLAMPED per-bench values. Clamping for display happens ONLY in explicitly-labeled display code
     (`signed_score.display_clamp`), never in stored metrics.
   - Update any unit tests that asserted the clamp; ADD a test: a below-chance bench (raw < baseline)
     stores a negative chance_corrected and a correspondingly lower composite.

2. ERROR-CONSISTENT + STRATIFIED web CIs — web/build_data.py:
   - The point and the CI must describe the SAME data. Build per-bench bootstrap inputs from ALL
     scored items: an item with `error` set OR `correct is None` (no answer) counts as INCORRECT
     (False) in the bootstrap inputs, exactly as the point estimate counts them. Keep reporting
     n_errors / n_no_answer separately for display.
   - Use REAL strata, identical to the CLI compare path: import `stratum_for_item` from
     `localbench.scoring.metadata` and compute each item's stratum; pass `BenchSample`
     `{correct, strata, chance}` into `localbench.scoring.bootstrap.composite_ci`, and pass real
     strata into `per_bench_ci`. Do NOT invent a single per-bench stratum.
   - Recompute the per-axis POINT as `signed_score(raw_accuracy, chance_for_bench(bench))` UNCLAMPED
     (do not trust a possibly-clamped stored value), and the composite POINT as the equal-weighted
     mean of the unclamped per-axis points. Keep the cross-check against the run's stored `composite`
     but as a WARNING only (current above-chance data will still match within 1e-6; below-chance
     legacy runs may differ because they were stored clamped).
   - Display scaling stays 0..100; the UI may show clamped values but the stored web JSON keeps the
     raw signed `*_raw` fields already present.

3. Tests — cli/tests/test_web_build_data.py (extend):
   - Assert errored/no-answer items lower the CI (e.g. a synthetic run with an errored item yields a
     CI/point consistent with counting it wrong).
   - Assert strata come from `stratum_for_item` (e.g. genmath composite CI uses category|difficulty|
     template strata, not a single stratum) — at minimum assert build_data calls it / that two items
     with different suite difficulty land in different strata.
   - Determinism preserved (seeded). Full suite stays green.
</task>

<action_safety>
Touch ONLY: cli/src/localbench/_scoring.py, web/build_data.py, and their tests
(cli/tests/test_scoring*.py / test_web_build_data.py). Reuse existing scoring modules — do NOT
duplicate stats. Do NOT modify the runner, providers, suite items, suite.json, the Next.js app
(web/app, web/components, web/lib), or re-run benchmarks. No git commits.
</action_safety>

<completeness_contract>
Done = full pytest green via cli/.venv; `cli/.venv/Scripts/python.exe web/build_data.py` runs clean;
stored chance_corrected is unclamped everywhere (no `max(0.0, …)` on stored metrics); web CIs count
errors/no-answer as incorrect AND use stratum_for_item strata; for the CURRENT committed data the
home composite points are unchanged (all models are above chance) and the composite cross-check passes.
</completeness_contract>

<verification_loop>
Run pytest; run build_data.py; print the index composites before/after and confirm the four anchors +
Qwen are unchanged at the point level (above-chance) while CIs now reflect strata + errors. Construct
a tiny synthetic below-chance case to confirm negative storage. Fix anything inconsistent before finishing.
</verification_loop>

<missing_context_gating>No questions. If a stratum cannot be resolved for an item, fall back to the
bench name as its stratum and note it in a comment.</missing_context_gating>

<compact_output_contract>
Final: (1) files changed, (2) pytest line + build_data result, (3) before/after index composite points
(prove above-chance unchanged) and one example of a now-stratified CI, (4) <=6 bullets: the single
signed-score definition reused, how errors enter the CI, where display clamping now lives, the
below-chance test result, any fallback used.
</compact_output_contract>

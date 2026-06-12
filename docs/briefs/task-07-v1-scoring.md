<task>
Implement the v1 rigorous scoring layer for local-bench per docs/scoring-methodology.md (v2,
red-teamed). This REPLACES the v0-simple composite math with statistically defensible methods.
It is a new analysis module operating on saved run records; it must not change the run-capture
format (cli/src/localbench captures raw items + usage already).

New module cli/src/localbench/scoring/ (separate from the live scorers in scorers/):

1. signed_score.py — per-bench/per-domain SIGNED chance-corrected score:
   s = (raw - c)/(1 - c), NOT clamped (negative allowed). Provide a display_clamp(s) helper
   for UI only. Document: inference/CIs use signed; clamp is cosmetic.

2. bootstrap.py — stratified/paired bootstrap (no Wilson, no quadrature):
   - per_bench_ci(item_correct: list[bool], strata: list[str], iters=10000, seed=int) ->
     {point, lo, hi} via stratified resampling within strata (subject/template/difficulty).
   - composite_ci(bench_to_items: dict, weights: dict, seed) -> nested bootstrap (resample
     items within each bench per draw, recompute weighted composite) → {point, lo, hi}.
   - All bootstrap is SEEDED + deterministic (pass seed in; do NOT call random/time at import).

3. paired_delta.py — THE core quant-comparison (methodology §1, §4):
   - Input: two run records over the SAME item ids (e.g. FP16 vs Q4). Align by item id;
     error if item sets differ.
   - per_item_delta (correct_A - correct_B in {-1,0,1}); paired bootstrap over items (and
     strata) → paired delta point + CI. Use this, NOT two independent CIs subtracted.
   - Return BOTH: repeatability_ci (run-to-run, same items — tight) and generalization_ci
     (item-universe — wide), clearly labeled, per methodology's three-estimand rule.
   - Per-DOMAIN deltas + worst_axis (largest single-domain regression with its CI).
   - Honest-label helper: format a delta as "−X.X ± Y on these items" (never universal %).

4. subgroups.py — difficulty/subject/template stratified deltas + a
   severe_subgroup_regression flag (any stratum whose delta CI is wholly below -threshold),
   to catch the Simpson's-paradox case the red-team raised.

5. A thin CLI: `localbench compare RUN_A.json RUN_B.json [--out cmp.json]` printing the
   paired composite delta, per-domain deltas, worst axis, both CIs, and any subgroup-regression
   flags. (Add as a subcommand alongside `run`.)

6. Tests (cli/tests/test_scoring_v1.py): synthetic fixtures with KNOWN answers —
   - signed score sign/scale incl. sub-chance negative;
   - bootstrap CI coverage on a known Bernoulli (CI brackets truth ~95% over seeds);
   - paired delta: identical runs → delta 0 with tight CI; a planted 1-domain regression →
     detected in worst_axis + subgroup flag, invisible in composite (prove the §6 point);
   - determinism: same seed → identical CIs.
</task>

<action_safety>
Only add cli/src/localbench/scoring/* , extend cli/src/localbench/cli.py with the `compare`
subcommand, and add cli/tests/test_scoring_v1.py. Do NOT modify the live scorers/, the runner,
the orchestrator's run-capture, suite/v0, or docs (except you MAY add docs/scoring-impl-notes.md
describing exact formulas/seeds used). No git. No network.
</action_safety>

<completeness_contract>
Done = full pytest green via cli/.venv (existing 118 + new); `python -m localbench compare
--help` exits 0; the planted-regression test proves composite-hides-it while worst-axis+subgroup
catch it; all CIs deterministic under a fixed seed.
</completeness_contract>

<verification_loop>
Run the suite; verify determinism (run the CI twice, assert identical) and the bootstrap
coverage test yourself. Numerical methods must be reproducible — no unseeded randomness.
</verification_loop>

<missing_context_gating>No questions. Use numpy if already available; else pure-Python stdlib random with a seeded Random instance (preferred — keep deps thin). Note which.</missing_context_gating>

<compact_output_contract>
Final: (1) files, (2) pytest line, (3) the planted-regression test result (composite delta vs
worst-axis delta numbers), (4) <=6 bullets on statistical choices + any deps added.
</compact_output_contract>

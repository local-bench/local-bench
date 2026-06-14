<task>
Build the DISCRIMINATION ANALYSIS HARNESS for the local-bench suite-v1 probe (Leg A: between-model
discrimination -> axis keep/weight). It reads a set of localbench run records (one per model run on
suite/v1) and outputs, per AXIS, the measured discrimination + a keep/drop verdict + a suggested weight.
This is ANALYSIS CODE ONLY — do not run any model or spend; the manager runs the actual probe.

Repo root: C:/Users/Michael/local-bench (cwd). Venv: cli/.venv (./.venv/Scripts/python.exe from cli/).
</task>

<context>
- Run-record format (localbench RunRecord JSON; see runs/probe-v1-gpt55.json or runs/anchor-*.json):
  each has `benches` {bench_name: {raw_accuracy, chance_corrected, n, n_errors, n_extraction_failures}},
  `composite`, and `items` [{id, bench, correct (bool), ...}]. The axis->benches mapping is in
  suite/v1/suite.json under `axes` {axis: {benches: [...], weight: null}}.
- Purpose (methodology): measure whether each axis SEPARATES models, so we keep + weight axes by MEASURED
  discrimination, not assumption (v0 failed because saturated axes were averaged in).
- Models are labeled anchors (frontier) vs locals (small/open). Labeling comes from a small input JSON:
  run_file -> {label: "anchor"|"local", model_name}.
- Per axis, a model's axis score = the item-count-weighted mean of its benches' chance_corrected over the
  benches in that axis.
- KEEP/WEIGHT rules (from the DECISION doc):
    * DROP if the ANCHORS cluster within ~3 pts (max_anchor - min_anchor <= 0.03 on the 0..1
      chance-corrected scale) OR if ALL locals floor near chance (every local <= ~0.05 chance-corrected).
    * Otherwise KEEP; suggested weight is proportional to the measured floor->frontier spread
      (max over ALL models - min over ALL models) of the axis score, normalized across kept axes to sum to 1.
- Secondary diagnostic: per-item point-biserial discrimination = correlation between item correctness
  (0/1 across the N models) and model overall composite (across the N models); report the axis mean. State
  explicitly that with few models this is a weak/indicative statistic.
</context>

<deliverables>
1. cli/src/localbench/probe/ (new subpackage) with discrimination.py exposing pure functions that take the
   loaded run records + the axis map + the labels and return a structured per-axis result:
   {axis, benches, anchor_min, anchor_max, anchor_spread, local_min, local_max, overall_spread,
    mean_point_biserial, verdict ("keep" | "drop:frontier-flat" | "drop:locals-floor"), suggested_weight}.
   Never crash on missing benches/items/labels — skip with a recorded note.
2. A CLI entry `python -m localbench.probe --runs <dir-or-files...> --labels <labels.json>
   --suite-dir suite/v1 --out probe-legA.json` that prints a readable per-axis table AND writes the JSON.
   Implement as a __main__ in the probe package; do NOT modify cli.py's run/compare commands.
3. cli/tests/test_probe_discrimination.py — unit tests on SYNTHETIC run records: a saturated axis (all
   models ~1.0) -> drop:frontier-flat; a discriminating axis (anchors high/spread, locals lower) -> keep
   with positive weight; a locals-floor axis -> drop:locals-floor; kept-axis weights sum to ~1.0.
</deliverables>

<action_safety>
Touch ONLY: cli/src/localbench/probe/** (new), cli/tests/test_probe_discrimination.py. Do NOT edit cli.py,
_scoring.py, _suite.py, scorers/**, suite/, web/, or any existing test. No network, no model runs.
</action_safety>

<verification_loop>
From cli/: ./.venv/Scripts/python.exe -m pytest tests/test_probe_discrimination.py -q must pass and the
full suite ./.venv/Scripts/python.exe -m pytest -q must stay green. Report counts.
</verification_loop>

<completeness_contract>
Report: the module API, the CLI usage line, the keep/weight rule as implemented, and the synthetic-test
results. Do NOT run any real model or spend.
</completeness_contract>

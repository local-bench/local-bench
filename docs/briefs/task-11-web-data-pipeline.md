<task>
Build the static-data pipeline for the local-bench web prototype: a Python script that turns
the canonical run JSONs in `runs/*.json` into the small, web-ready static JSON the Next.js app
will read. NO web framework here — this brief is the data layer only.

Reuse the AUTHORITATIVE scoring already in the repo — do NOT reinvent statistics:
- `localbench.scoring.bootstrap`: `composite_ci(bench_to_items, weights, seed, iters)` and
  `per_bench_ci(item_correct, strata, iters, seed)` both return `{point, lo, hi}`.
- `localbench.scoring.signed_score`: `signed_score(raw, chance=...)`, `chance_for_bench(bench)`,
  `CHANCE_BASELINES`. The composite is the EQUAL-WEIGHTED mean of per-bench chance-corrected
  (signed) scores (verified: mean(0.663, 0.84, 1.0) == 0.834 == a run's `composite`). Use equal
  weights {genmath:1, ifeval:1, mmlu_pro:1}.

Run JSON schema (read the files to confirm; key fields):
- top: `schema`, `manifest`, `benches`, `composite` (float 0..1), `items[]`, `totals`,
  `warnings`, `estimated_cost_usd`.
- `benches[name]`: {n, n_errors, n_extraction_failures, raw_accuracy, chance_corrected}.
- `items[]`: {id, bench, response_text, extracted, correct(bool), latency_seconds, usage, error}.
- `totals`: {n_items, n_errors, prompt_tokens, completion_tokens, total_tokens,
  wall_time_seconds, completion_tokens_per_second}.
- `manifest`: {schema_version, suite{suite_version,tier,lane,caps,item_set_hashes},
  endpoint{kind,runtime_reported_model,api_provider}, model{family,quant_label,file_name,
  file_size_bytes,file_sha256,format,...}, runtime{name,version,kv_cache_quant,ctx_len_configured,...},
  hardware{gpus[{name,vram_mb,driver}],cpu,ram_gb,os}, sampling{temperature,thinking_mode,by_bench},
  execution, integrity}. Many model/* fields are null in current runs — handle gracefully.

1. CURATION CONFIG `web/data_sources.json` (committed): an explicit list of which runs appear on
   the site plus display metadata the raw runs lack. Schema per entry:
   {file, kind: "anchor"|"community", model_label, family, quant_label (nullable),
    vram_footprint_gb (nullable number; for the scatter x-axis), reasoning_lane (nullable string
    override), notes (nullable)}. Create a STARTER config containing the four Qwen-9B community
    runs we have: runs/quick-9b-run1.json, quick-9b-var1.json, quick-9b-var2.json,
    quick-9b-var3.json — all model_label "Qwen3.5 9B", family "Qwen3.5", kind "community",
    quant_label null, vram_footprint_gb null, notes "repeatability set (4 identical-config repeats)".
    (Anchor entries will be appended later by the manager once full anchor runs land — design the
    script so adding entries + rerunning is the only step.)
   Resolve model identity in this priority: explicit model_label from config > model.family+quant_label
   > endpoint.runtime_reported_model > endpoint.api_provider+suite. Slugify model_label for URLs.

2. `web/build_data.py` (committed): reads `web/data_sources.json`, loads each run JSON, and for each:
   - group `items` by bench into correct-lists (skip items with error set or correct is None;
     count them as incorrect for accuracy but record n_errors/n_no_answer separately so the UI can
     show data quality);
   - per-axis: point = benches[bench].chance_corrected; CI = map raw per_bench_ci bounds through
     signed_score(raw, chance_for_bench(bench)) so the interval is on the chance-corrected scale;
   - composite: composite_ci({bench: correct_list}, equal weights, seed=20260612); assert its point
     is within 1e-6 of the run's stored `composite` (else emit a warning into the output, do not crash);
   - carry through: tier, lane, thinking_mode, tokens (prompt/completion/total), median & p95
     completion tokens-per-item ("tokens-to-answer") computed from items[].usage, tok/s, wall_time,
     estimated_cost_usd, hardware summary (gpu name+vram, os), runtime summary, quant_label, vram_footprint_gb.
   - Scale all displayed scores to 0..100 (keep raw 0..1 too).
   Emit (pretty-printed, stable key order):
   - `web/public/data/index.json`: {generated_note, suite_version, models:[ one row per model =
     its BEST run by composite: {slug, model_label, family, kind, best_run_id, composite{point,lo,hi},
     axes{genmath,ifeval,mmlu_pro}{point,lo,hi}, tier, lane, n_runs, tokens_to_answer_median,
     est_cost_usd, replicated(bool = n_runs>=3 for community, always true for anchor)} ] }.
   - `web/public/data/models/<slug>.json`: {slug, model_label, family, kind, runs:[ per run:
     {run_id, quant_label, vram_footprint_gb, composite{point,lo,hi}, axes{...}, tier, lane,
     tokens_to_answer_median, tok_s, est_cost_usd, hardware, runtime, n_items, n_errors} ] } —
     this is the scatter source (quality vs vram_footprint; anchors have null footprint -> the app
     draws them as reference lines).
   - `web/public/data/runs/<run_id>.json`: full per-run detail = {run_id, model_label, kind,
     composite{point,lo,hi}, axes{ each: {point,lo,hi,raw_accuracy,n,n_errors,n_no_answer} },
     worst_axis (lowest chance-corrected point), manifest_summary{model,quant,runtime,hardware,
     lane,thinking_mode,caps,sampling}, totals, est_cost_usd, item_set_hashes, suite_version}.
   - run_id = slug + "__" + the run file stem (stable, filesystem-safe).
   Use the cli venv interpreter for imports (the script must run via
   `cli/.venv/Scripts/python.exe web/build_data.py` from repo root; insert cli/src on sys.path if needed).

3. Test `cli/tests/test_web_build_data.py`: running the pipeline on the committed data_sources.json
   produces the three output kinds; composite point in index matches each run's stored composite
   within 1e-6; every model in index has a models/<slug>.json and every best_run_id has a
   runs/<id>.json; CIs satisfy lo <= point <= hi; output is deterministic across two runs
   (seeded bootstrap). Keep iters modest (e.g. 2000) in the test for speed if needed, but the
   script default can be 10000.
</task>

<action_safety>
Create only: web/build_data.py, web/data_sources.json, web/public/data/** (generated outputs),
cli/tests/test_web_build_data.py. Do NOT modify cli/src scorers/runner/providers, suite/, or any
run JSON. No network. No git commits. Add web/public/data/ generated files to git is the manager's
call — you just generate them.
</action_safety>

<completeness_contract>
Done = `cli/.venv/Scripts/python.exe web/build_data.py` runs clean and writes index.json,
at least one models/<slug>.json, and one runs/<id>.json under web/public/data/; the new test is
green via `cli/.venv/Scripts/python -m pytest cli/tests/test_web_build_data.py -q`; full suite
still green; composite-match assertion passes for all four Qwen runs.
</completeness_contract>

<verification_loop>
Run the script, then the test, then the full suite. Open index.json and one models/ and one runs/
file and eyeball: Qwen3.5 9B present with composite ~83, three axes with CIs, 4 runs on the model
page. Fix anything that doesn't match before finishing.
</verification_loop>

<missing_context_gating>No questions. Pick sensible defaults and note them in a header comment in build_data.py.</missing_context_gating>

<compact_output_contract>
Final: (1) files created, (2) the pytest line, (3) the exact output JSON shape for index.json
(top-level + one model row) and runs/<id>.json, (4) <=6 bullets: identity-resolution order,
how anchors-as-reference-lines is encoded, the composite-match check result, any null-field handling.
</compact_output_contract>

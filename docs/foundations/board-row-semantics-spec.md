# Build spec: board per-quant SYSTEM rows (row-semantics fix)

## Context
`board_v1.json` is the immutable, scorer-side release artifact; the site is a pure renderer.
The generator lives in `cli/src/localbench/scoring/board_scoring.py` (+ `board_types.py`,
`board_sources.py`, `board_support.py`, `board.py`, `board_manifest.py`). Tests:
`cli/tests/test_board.py`, `board_fixtures.py`, `test_board_manifest.py`. The CLI venv is
`<home>\local-bench\cli\.venv\Scripts\python.exe` / `pytest.exe` (run from `cli\`).

## Problem (oracle launch flag)
`model_rows()` collapses each family's quant ladder to its single best run
(`best = max(group, key=composite_raw)`) and emits ONE row with `n_runs` but **discards every
non-best quant's scored data**. The `Qwen3.6-27B` row shows only Q6_K's 75.25; Q2/Q3/Q4/Q8 are
absent. This (a) labels a family-best as a "system", and (b) hides local-bench's core finding
that the ladder plateaus at Q4 (74.9 ~= Q6 75.25). Each `ScoredRun` is ALREADY fully scored in
`_scored_run`; `model_rows` just drops all but the best.

## Goal
Expose every quant as a first-class SYSTEM inside the immutable artifact, while keeping the
default `models` list ONE ROW PER FAMILY (uncluttered leaderboard). Decouple data-completeness
(correctness, do now) from the headline-quant display choice (taste, defaulted + flagged).

## Changes (ADDITIVE ONLY)

### 1. Propagate quant identity into `ScoredRun` (`board_types.py`, `board_scoring.py`)
- Add to `ScoredRun`: `quant_label: str | None`, `run_id: str` (== the `{slug}__{stem}` value
  currently stored as `best_run_id`).
- In `_scored_run`, set `run_id` and copy `source["quant_label"]`. (Keep `best_run_id` for
  backwards-compat of the per-run id, or rename internally — but the FAMILY row's `best_run_id`
  must keep meaning "the family's best quant run id".)

### 2. Curated `recommended` quant (`board_types.py` `CuratedSource`, `board_sources.py`)
- Add optional `recommended: bool` to `CuratedSource` (default `False`), read from the curation
  source JSON (`bool_or_false`). This marks the human-judged plateau/value quant per family.
- The plateau pick is a JUDGEMENT (where the VRAM/score curve flattens), NOT a mechanical CI
  test — so it is curated, not auto-computed. Validate: at most ONE `recommended: true` per
  family group; if zero, recommended := best.
- For the Qwen3.6 family, the curation should mark `Q4_K_M` as `recommended` (the plateau/value
  pick). Update the curation source file accordingly IF it is in-repo and you can identify the
  Qwen Q4_K_M entry unambiguously; otherwise leave a clear TODO in your report.

### 3. Emit `systems[]` per family row (`model_rows` in `board_scoring.py`)
For each family group, keep emitting ONE row (one per family) but:
- Family `composite` / `axes` / ranking-relevant fields stay = the BEST quant's values
  (ranking integrity preserved: a family ranks by the best it achieves on the suite).
- `n_runs` stays = number of quants in the family.
- ADD `best_system_run_id` = best quant's `run_id`.
- ADD `recommended_system_run_id` = the curated recommended quant's `run_id` (or best if none).
- ADD `systems: list[JsonObject]`, one entry per quant in the group, sorted by `composite_raw`
  desc (best first). Each entry:
  `{quant_label, run_id, composite, axes, tier, lane, ranked, n_runs (==1), replicated,
    score_status, tokens_to_answer_median, tokens_to_answer_p95, latency_s_median,
    wall_time_seconds, est_cost_usd, is_best (bool), is_recommended (bool)}`.

### 4. Headline policy (DEFAULT — user-tunable; FLAG it, do not over-bake)
- Rank families by BEST quant (unchanged). The family row IS the best quant for ranking +
  headline number. `recommended_system_run_id` is an annotation only; it MUST NOT change rank
  order. Record this default choice in your report as a flagged, reversible decision.

### 5. Parity must stay ZERO divergence
- The board-vs-index parity check compares FAMILY-level composites. `systems[]` is additive and
  MUST NOT enter parity (the web index has no per-quant rows). Confirm parity stays zero
  divergence after the change.

### 6. Tests
- Extend `test_board.py` / `board_fixtures.py`: a family fixture with >=3 quants where Q4 ~= Q6
  (within CI) and Q3 lower, with Q4 curated `recommended`. Assert: exactly one family row;
  `systems` length 3, best-first; `best_system_run_id` == Q6 entry; `recommended_system_run_id`
  == Q4 entry; `is_best`/`is_recommended` flags correct; `n_runs == 3`; parity zero divergence.
- Keep ALL existing board + full-suite tests green.

## Deliverables
- The code change (additive) + tests.
- Regenerate `cli/runs/board/board_v1.json` from the existing curated runs to show the new
  `systems[]` arrays (gemma still skipped-as-missing is fine). Report the new
  `board_sha256` and a short diff summary of the Qwen3.6 row's new fields.
- Run board tests AND the full venv pytest; report pass counts.

## Hard constraints
- ADDITIVE. Do NOT change `axes.py`, scorecard logic, the scorer, `top_k`, decoding lanes, or
  anything under `web/`. Do NOT change the family-level composite or the rank order. Do NOT
  `git push` or `git commit`. Do NOT modify run artifacts other than regenerating
  `board_v1.json`/`board_v1.manifest.json` via `localbench board`.
- If anything forces a non-additive change or a parity divergence, STOP and report rather than
  work around it.

# Build spec: scorer-side `board_v1.json` generator (v1 release artifact)

## Mission
Move ALL score computation into the scorer and emit ONE immutable `board_v1.json` that the
website renders verbatim. Today the web build (`web/build_data.py`) computes composite/axis
scores from the run JSONs; for v1 the site must become a PURE renderer. You build the
generator + a `localbench board` subcommand that produces `board_v1.json` plus a release
manifest. This is the credibility spine of the first public launch — correctness and
determinism matter more than cleverness.

## Hard constraints
- Work ONLY in `<home>\local-bench` (the repo). Use the venv:
  `<home>\local-bench\cli\.venv\Scripts\python.exe` (+ `pytest.exe`).
- ADD a new module (suggest `cli/src/localbench/scoring/board.py`) and a `localbench board`
  subcommand in `cli/src/localbench/cli.py`. Do NOT refactor the existing scorer, the
  `scoring.axes` registry, or `reasoning_registry.py`. Minimal, additive changes only.
- Do NOT touch anything under `web/`. You MAY READ `web/lib/schemas.ts`,
  `web/public/data/index.json`, `web/data_sources.json`, and `web/build_data.py` for parity,
  but never edit them.
- Do NOT run any GPU workload (no llama-server, no `localbench run`). You only read existing
  run JSONs and write the artifact.
- The artifact is PUBLISHED. It must contain ZERO operator identity: no local filesystem
  paths, no Windows user dirs (`C:\Users\...`), no username, no hostname, no git remote URLs,
  no machine-specific absolute paths. Strip/normalize anything like that out of run metadata
  before it enters the artifact. Add a test that greps the emitted artifact for these and fails
  if found.

## Inputs
- The canonical scoring lives in the CLI (`scoring.axes` registry = the single source of truth
  for axis keys, weights, headline-vs-candidate, and which benches roll into the composite) and
  the scorer module(s) under `cli/src/localbench/scoring/`. USE THE CANONICAL CLI SCORING. Do
  not re-derive weights by hand.
- Run JSONs in `cli/runs/`. The v1 board rows come from the capped-thinking headline-lane runs:
  the Qwen3.6-27B ladder (`ladder-qwen36-27b-{Q2_K,Q3_K_M,Q4_K_M,Q6_K,Q8_0}.json`),
  `ladder-qwen36-27b-qwopus.json`, and the gemma ladder file
  `ladder-gemma4-31b-Q4_K_M.json` (NOTE: this run is still in progress; if the file is absent or
  incomplete, the generator must skip it gracefully and still produce a valid board from the
  Qwen rows — do not hard-fail on a missing run). The off-family anchors
  (`anchor-granite-3.3-8b`, `anchor-r1-distill-llama-8b`, `anchor-nemotron-nano-4b`) are
  NON-RANKED reference rows — include them only if they are already represented in the current
  curation; otherwise ignore for v1. IGNORE everything under `cli/runs/_superseded-*`.
- Curation (which run files map to which board model + labels/family/quant) currently lives in
  `web/data_sources.json`. Read it to learn the mapping. If a clean programmatic mapping is
  awkward, accept an explicit curation/config input to `localbench board` (a small JSON listing
  run files + labels) rather than guessing — but default to reproducing the current
  `data_sources.json` selection so the board matches what the site shows today.

## Output 1: `board_v1.json`
Write to a deterministic repo path — suggest `cli/runs/board/board_v1.json` (create the dir).
It must be drop-in-consumable by the web against `web/lib/schemas.ts`. Shape (align field names
EXACTLY to `IndexDataSchema` + `IndexModelSchema` in `web/lib/schemas.ts`):

Top level:
- `generated_note` (string): say it was produced by `localbench board`, scorer-side, immutable.
- `schema_version` (string, e.g. "board-v1").
- `index_version` (string) — carry the registry/index version; bump rule is documented below.
- `suite_version`, `scoring_version`, `dataset_version` (strings) — pulled from the suite
  manifest + scorer + dataset pins. If a value has no current source, set it explicitly and note
  it; do not invent a hash.
- `lane_scope` (string): `"capped-thinking"` — the ranked board is headline-lane only.
- `generated_at` (ISO-8601 string) — wall-clock at generation is fine (this is a normal process,
  not a workflow script; `datetime.now(timezone.utc)` is allowed here).
- `models` (array): one entry per board model, each matching `IndexModelSchema`:
  `slug, model_label, family, kind, best_run_id, composite{point,lo,hi,point_raw?,...},
  axes{<axis_key>:{point,lo,hi,raw_accuracy,n,n_errors,n_no_answer,termination_rate?,
  conditional_accuracy?}}, tier, lane, n_runs, ranked, tokens_to_answer_median,
  est_cost_usd, replicated, score_status`.
- `manifest` (object): see Output 2 (you may embed a copy AND write the standalone file).

Scoring rules (use the canonical CLI scoring; verify against the registry):
- Composite = the registry-weighted combination of the VALIDATED headline axes (today Knowledge
  = MMLU-Pro and Instruction = IFBench, each 0.5). Read the weights from `scoring.axes`; do NOT
  hardcode 0.5 in a way that silently diverges from the registry.
- CIs: use the CANONICAL scorer CI — the stratified non-parametric **bootstrap percentile**
  helper (2.5/97.5 pct, seed 0, 10k iters) the scorer already uses for the headline composite.
  Do NOT use Wilson here — Wilson is ONLY the candidate-axis discrimination/promotion gate
  (`probe/gates.py`) and the experimental agentic ASR path, NOT the composite. Reuse the
  scorer's own composite + `signed_score` (chance-correction) + bootstrap-CI functions from
  `localbench.scoring` / `localbench._scoring`; do not re-implement a second method. Verified
  scoring identity to reproduce exactly: composite = equal-weight mean of the PRESENT headline
  axes computed on chance-corrected scores, where `corrected = (raw - chance) / (1 - chance)`;
  MMLU-Pro chance ~0.1092, IFBench chance 0.0; the registry import-time-asserts headline weights
  sum to 1.0.
- `ranked = true` ONLY for rows that are: capped-thinking lane AND conformance-pass AND measured
  (have real axis data). Anchors / answer-only / api rows: `ranked = false`. Candidate axes
  (weight 0) may appear as columns but MUST NOT change the composite.
- Surface failure/format quality per axis (or per run, your call — but expose it): include
  `n`, `n_errors`, `n_no_answer`, and the conformance rates that exist in the run JSONs
  (`leaked_reasoning_rate`, `truncation_rate`, `no_final_answer_rate`) — these feed the site's
  "raw scores + invalid/format/truncation beside the composite" requirement. If a run JSON lacks
  a field, emit null, don't fabricate.

PARITY CHECK (important): after generating, compare your computed composite + per-axis `point`
for each measured model against the corresponding measured row in the current
`web/public/data/index.json`. They should match within floating-point tolerance. If ANY row
diverges, do NOT silently ship it — print a clear DIVERGENCE report (model, field, board value,
index value) so the orchestrator can adjudicate whether the web build was computing scores
differently. Parity proves the move from web-compute to scorer-compute changed no numbers.

## Output 2: release manifest `board_v1.manifest.json`
A small sidecar (suggest `cli/runs/board/board_v1.manifest.json`):
- `board_sha256`: sha256 of the exact `board_v1.json` bytes as written.
- `suite_version`, `scoring_version`, `dataset_version`, `index_version`.
- `item_set_hashes`: the per-bench suite item-set hashes (from the suite manifest / run JSONs).
- `scorer_git_commit`: `git rev-parse HEAD` (short or full).
- `reasoning_registry_hash`: a stable hash of `reasoning_registry.py` content (or the registry's
  own version constant if one exists).
- `extractor_version`: the answer-extractor version if the code exposes one; else note absent.
- `generated_at`.
The manifest must be byte-stable for identical inputs (sorted keys, fixed float formatting) so
the same runs always produce the same `board_sha256` (except `generated_at` — exclude
`generated_at` from the hashed content OR document that it is included; prefer hashing
`board_v1.json` bytes which already contain it, and accept that re-runs differ only by time).
Cleaner: make `board_v1.json` deterministic by allowing a `--frozen-timestamp` flag; when
generating the release artifact we pass a fixed timestamp so the hash is reproducible.

## Provenance caveats (verified against current code — DO NOT fabricate)
- suite-v1 pins ONLY `temperature: 0` (greedy). `top_p` / `top_k` / `min_p` / `seed` are NOT
  pinned (they are null in the manifest; server defaults apply). Emit them as null; never claim
  they are pinned in the artifact or manifest.
- For plain local OpenAI-compatible endpoint runs the run manifest has `integrity.canonical =
  false`: `model.file_sha256` is `"UNHASHED"`, and quant label / runtime name+version / KV-cache
  quant / context length are NOT self-captured (they are operator/catalog-supplied via the
  curation). Emit what exists; pull `model_label`/`family`/`quant`/`runtime` from the curation
  (`web/data_sources.json`); null the rest with a short note. Never invent a hash or a version.
- Carry the live scorecard identity into the manifest by READING it from the scorer (do not
  hardcode): scorecard id (currently `scorecard-v1.3`), `registry_digest`,
  `reasoning_registry_digest`, scorer versions. Pull the real current values at generation time.

## CLI
`localbench board` subcommand. Flags: `--runs-dir` (default `cli/runs`), `--out` (default
`cli/runs/board/board_v1.json`), `--curation` (optional path to a curation JSON; default = derive
from `web/data_sources.json`), `--frozen-timestamp` (optional ISO string for reproducible hash),
`--check-parity/--no-check-parity` (default on; compares to `web/public/data/index.json`).
Exit non-zero on parity divergence unless `--no-check-parity`.

## Tests (add under `cli/tests/`)
1. The emitted `board_v1.json` validates structurally (keys/types) against the expectations of
   `IndexModelSchema`/`IndexDataSchema` (mirror the shape in a Python check; you needn't run the
   TS validator).
2. Only headline-lane, conformance-pass, measured rows are `ranked=true`; anchors/answer-only
   never ranked.
3. Composite equals the registry-weighted axis combination for a known fixture row (assert the
   weights come from `scoring.axes`, not a literal).
4. The manifest `board_sha256` matches a fresh sha256 of the written bytes; identical inputs +
   `--frozen-timestamp` reproduce the same hash.
5. Anonymity: the emitted artifact contains no `C:\\Users\\`, `/home/`, `/Users/`, the operator
   username, hostname, or `github.com`/`gitlab.com` strings.
6. Graceful skip: if `ladder-gemma4-31b-Q4_K_M.json` is absent, the board still generates from
   the Qwen rows and is valid.

## Done = 
Run the FULL existing test suite plus your new tests with the venv pytest and report the exact
pass/fail counts. Generate a sample `board_v1.json` + manifest from the CURRENT `cli/runs/`
(Qwen ladder; gemma may be missing — that's fine) and run the parity check, reporting any
divergence verbatim. In your final message: the test counts, the parity result, the list of
files you added/changed, and the emitted `board_sha256`.

# Work order: per-model benchmarking-time panel (owner request 2026-07-24)

Owner: "the home page has a section showing time taken for each model benchmarked —
do this for each model page too. For qwen3-6-27b, rank all benchmarked runs on time
taken to benchmark."

## What to build

New component `web/components/model-bench-time-panel.tsx` rendered on every model
page, ranking every measured CURRENT-LANE run of that model's family by wall time.
Unlike the landing panel (which deliberately sorts by leaderboard rank), the owner
explicitly wants this one **sorted by time taken, ascending (shortest first)**.
Within one family that is an honest cost ladder, but KEEP the landing panel's
misread guard verbatim in visible text: "Elapsed time for this exact full-suite
run; not a general model-speed measurement." — and keep the "not an
inference-speed ranking" sentence in the header copy.

## Row sources (mirror the model scatter's eligibility exactly)

Reference implementation: `web/components/model-scatter.tsx` (`toScatterRun` +
`toCommunityScatterRun`) and the landing panel
`web/components/replication-time-panel.tsx` (row layout, bars, formatDuration,
flame on shortest, tooltip with hardware).

1. This model's own baked runs: `model.runs` where lane === HEADLINE_LANE
   (`web/lib/leaderboard-score.ts`), complete per the same isCompleteRun logic
   model-scatter uses, and wall_time_seconds > 0. Label = quant_label (own-page
   context needs no model name).
2. Family variant baked runs (`familyModels` prop, same shape ModelScatter takes):
   same eligibility. Label = `variantNameInContext(familyModel.model_label,
   model.model_label)` + " · " + quant (`web/lib/model-name.ts`).
3. Live community rows (the `communityRows` the page already hydrates — consume the
   SAME rows `ModelPageCommunityViews` passes to ModelScatter/ModelVariantBoard in
   `web/components/model-page-community.tsx:50-59`; do NOT add a second fetch):
   headlineComplete && compositeFull !== null && perf?.wall_time_seconds > 0.
   Label = same compact-label rules as toCommunityScatterRun (quant-only for this
   model's artifacts, compact variant name otherwise, "declared as" only when
   `declaredNameIsRedundant` says the declared name is genuinely different).
   Artifact join via `communityArtifactDetailForSha`
   (`web/lib/community-artifact-details.ts`).

A live row and a baked run are DISTINCT benchmarked runs — if both exist for the
same artifact, both rows render (they are different runs with different receipts).

## Row content (converge with the landing panel's visual language)

- Label (as above) + composite score (baked: run.composite.point via the same
  display the landing panel uses; live: communityScore(compositeFull)).
- Horizontal time bar scaled to the panel max, formatDuration value, flame emoji
  on the single shortest run (reuse the landing panel's run-oriented copy:
  "Shortest full-suite run this season" — never "fastest model").
- Tooltip/title: submitter hardware for live rows when present (formatGpuShort);
  baked rows imply the reference rig. Landing panel's hardwareLabel pattern.
- Link each row: baked runs with run_id → runHref(run_id) (`web/lib/routes.ts`);
  live rows → row.detailPath when non-null.

## Render rules

- Render the panel only when ≥ 2 eligible timed rows exist (a one-row ranking is
  noise); otherwise render nothing (no empty-state card).
- Placement: inside `ModelPageCommunityViews` in
  `web/components/model-page-community.tsx`, directly AFTER the ModelScatter and
  BEFORE the ModelVariantBoard, so it hydrates live rows for free.
- Title: "Benchmarking time" (same name as the landing panel — cross-artifact
  naming consistency, owner renamed it from "replication time" 07-23). Subtitle
  scope line: "measured full-suite runs · wall time on each run's rig".

## Constraints

- Client zod board-adapter schema is a security boundary — DO NOT touch
  `web/lib/board-adapter.ts`; everything needed is already adapted.
- No new fetches; no functions/ changes; no schema changes. Pure presentation.
- Tests required (vitest, follow `web/tests/replication-time-panel.test.tsx`
  patterns): (a) ascending time order; (b) baked + family + live rows all render
  with correct labels (quant-only for own runs, compact for variants); (c) legacy
  capped-thinking-lane runs are EXCLUDED (this is the critical honesty rule —
  legacy lane wall times are not comparable to bounded-final); (d) hidden when
  fewer than 2 timed rows; (e) single flame on the shortest; (f) misread-guard
  copy present.
- Gates before done: `npx tsc --noEmit`, `npm run test` (check counts, do not
  trust piped exit codes), `npm run build` — all from web/.
- Do not deploy; the orchestrator reviews, deploys, and live-verifies.

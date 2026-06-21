# Site overhaul plan — 2026-06-20 (local-bench `web/`)

Durable, committed plan so it survives session loss (we lost a session to a crash today —
this is the recovery anchor). Branch `suite/v1-quant-wedge`, commits **LOCAL — do not push**.
Standing rule: no GPU work on the local RTX 5090 without Michael's explicit go — **this plan
needs none** (the progress feature is verified with fixtures/mocks).

## Goal & framing
Launch-ready quality, iterated **locally**. Actual deploy (Vercel/Supabase) stays **deferred**
until Michael says go. Prioritise polish + filling real gaps over shipping infra. **Targeted**
visual redesign of high-impact surfaces + a consistency/a11y pass — **keep the dark `bench-*`
identity** (no rebrand, no new palette direction).

## Locked decisions (from the grill, 2026-06-20)
1. **Driver:** launch-ready, no deadline; deploy deferred.
2. **Visual ambition:** targeted redesign + a11y; preserve the `bench-*` identity.
3. **Progress bar:** CLI TTY bar **and** a dev-mode web live-view. The runner writes an
   incremental `runs/{id}.progress.json`; the web view polls it client-side (works in
   `npm run dev` now; points at a real endpoint post-deploy).
4. **Submit:** build the **full upload UI now** — drag/drop or pick a `localbench run` JSON,
   validate client-side against `web/lib/schemas.ts` (zod) + render a preview, with the actual
   network upload **mocked** until the Track-2 backend. Bounty CLI → generated from config.
5. **Execution:** this committed doc → one task at a time → per-task gate → checkpoint commit.
   Foundation-first order.

## Guardrails ("don't create issues")
- **Presentational / additive only.** NEVER alter scoring, methodology semantics, or the
  deterministic data pipeline.
- **Keep `output: "export"`** (static export). Dev-mode polling is compatible — do NOT switch
  to SSR / a runtime server.
- **Progress instrumentation must not perturb run outputs:** the scored run JSON must be
  byte-identical with/without progress writing. Progress writes go to a **separate**
  `*.progress.json`, never the scored run file.
- If `web/build_data.py` is ever touched: re-run it and confirm `git diff --stat public/data`
  shows **no change** (byte-identical) — proves behaviour preserved.
- **Per-task verification gate** (all green before the checkpoint commit):
  - Web: `cd web && npm run typecheck && npm test && npm run build` (+ `npm run e2e` for
    interactive / route changes).
  - CLI/runner: `cd cli && .venv\Scripts\python.exe -m pytest tests -q` (currently 624 green).
  - Visual: load each affected route at http://localhost:3000 and eyeball it.
- **Checkpoint commit after each task** with a clear message. Local only; do not push.

## Assumptions (flag if wrong)
- Design against the **current demo/shell data**; must be graceful at any data density (empty
  shells → fully measured). Real runs slot in later via the normal build.
- Keep the public headline **"Local Intelligence Index (v1 · Core Text)"** unless changed.
- **No GPU required**; the progress feature is verified with a mock endpoint (`--max-items`) +
  a hand-authored progress-JSON fixture. A real long run is Michael's to trigger later.

## Re-sequence + new scope (2026-06-21, post-oracle consult)
After T1, the Core Text campaign hit **STRONG GO** (real Qwen3.5 ladder: composite 0.8B 17.8 → 2B
37.8 → 4B 59.9 → 9B 69.1). That flips the site from scoreless shell to a **live** Local Intelligence
Index, so we PIVOT: make the data real before the visual redesign. (GPT-5.5 Pro oracle consult, slug
`site-proceed-scatter`; brief at `%TEMP%\oracle-site-consult-brief-2026-06-21.md`; answer synthesised
in chat.) Decisions:
- **Data path = build-time aggregation; NO runtime DB/API** (would break static export). `best_run_id`
  is already a build-time argmax. A DB only LATER, as a back-office ingestion source that STILL exports
  static JSON; the published artifact stays static.
- **Distills / fine-tunes / merges = SEPARATE models (their own scatter points).** Quants / runtime /
  config = variant-runs competing for ONE point per model. (Add optional model-level lineage metadata
  — `base_model_slug`, `lineage_kind` — later.)
- **IFBench 3-column decomposition** (Strict = Termination × Conditional) wired as OPTIONAL,
  PROVISIONAL-aware structure; never hardcode numbers; render "pending" until status=final. Field names
  are a **CROSS-LANE CONTRACT** — reconcile with the campaign agent's `cli/` output, do NOT invent.
- **Never derive the composite in the web layer** — trust the pipeline's `composite`/`axes`.

### Revised order
T0 ✅ · T1 ✅ · T1.6 scatter ✅ · T1.6b table ✅ · oracle hardening ①②④⑤⑥ ✅ · IFBench display ③ ✅ ·
**NEXT (gated on the campaign handoff): wire strict ladder → public/data → methodology/trust copy →
full gate → T2.**

#### Session 2 status (2026-06-21, post-oracle) — all data-independent steps DONE + committed
Commits: `d10b004` (scatter eligibility/frontier/x-domain) · `df36483`→`5e0c4ac` (data contract,
reconciled to cli) · `566a442` (quant Δ demote) · `dce064b` (copy seam) · `b0ab728` (integrity test) ·
`614ee83` (IFBench 3-col display). The scatter / table / leaderboard / IFBench decomposition render
gracefully EMPTY today and go LIVE the moment the campaign agent re-emits strict-scored run JSONs
(bench aggregates carrying `termination_rate` + `conditional_accuracy`; `raw_accuracy` = strict) +
wires `data_sources.json` + rebuilds `public/data`. Field names already reconciled to
`cli/_scoring.py` (see `SITE-DATA-CONTRACT.md`). T2 visual redesign waits for the real ladder.

### T1.5 — Live LII data contract ("make it real")
Data-INDEPENDENT parts (do NOW, my lane):
- IFBench 3-col display component with provisional / "pending" + a "provisional — strict re-score
  pending" badge until `status: "final"`.
- Demote / relabel the `quant-decision-matrix` "Δ vs baseline" QUALITY column (methodology §6: the quant
  story is VRAM + speed + drift, not an accuracy wedge) — even before KLD data exists.
- Optional `diagnostics.ifbench_termination` schema on `AxisScore` (provisional-aware), pending
  field-name reconciliation with `cli/`.
- Data-integrity build assertion (vitest/build): every measured `best_run_id` resolves to a run; the
  selected run's composite is non-null; measured rows are not `demo`.
- Home/leaderboard copy seam: when measured data is present, drop the "scoreless catalog" framing; keep
  "Local Intelligence Index v1 · Core Text" (no "overall intelligence" overclaim).
Data-DEPENDENT parts (on campaign handoff of the strict-re-scored run JSONs): wire the ladder via
`data_sources.json` + `build_data.py`, rebuild `public/data`, flip IFBench status → final.

### T1.6 — Best-variant scatter (landing page)
New `BestVariantVramScatter` (hand-rolled SVG, reuse the existing `quality-vram-scatter` patterns —
proven, low-risk). One point per model = its best MEASURED run (argmax composite; tie-break VRAM →
tok/s → run_id; exclude demo/missing; within the rankable lane; anchors = dashed reference LINES, not
points; distills = own points). Axes: LII composite (y, 0–100) vs effective VRAM required
`vram_required_gb_8k` (x, log2); GPU-tier lines 24/48/80 GB; CI whiskers; label the Pareto frontier +
top-N, the rest hover dots; subtle frontier line; mobile = horizontal scroll + a "best fits
24/48/80 GB" list. Derive `bestVariantPoints` in `getHomePageData()`. MVP first; big-graph (d3-scale +
filters + collision labels + click-through + synced table) later.

### Minimum honestly-launchable set (gate for "live")
1. Real ladder in static data; no "scoreless" claim. 2. CI framing on every score; no "overall
intelligence". 3. IFBench structure with provisional rendering; no hardcoded numbers. 4. demo/missing
visually distinct or excluded from ranking. 5. quant copy no longer centers accuracy-delta. 6. static
export intact. 7. the data-integrity build assertion passes.

### Lane discipline (shared tree)
`web/public/data` is produced from campaign outputs → treat it as a **scheduled handoff**, not a shared
scratchpad; one agent edits it at a time. I don't touch `cli/` or `docs/foundations/`; they don't touch
`web/`. Avoid `web/build_data.py` unless the optional IFBench fields can't pass through (then enforce
byte-identical output). `git status` + inspect generated diffs before every commit.

## Tasks (foundation-first detail — order now superseded by the re-sequence above)

### T0 — Plan doc (this file)
Write + commit. **← committing now.**

### T1 — Design-system + a11y foundation
Cleans the tokens first so no later visual work has to be reworked.
- Promote stray hardcoded colours (amber / emerald / zinc, `white|black` opacities) that carry
  semantic intent into named `bench-*` tokens in `tailwind.config.ts`; replace usages.
- Add real `focus-visible` rings for keyboard nav (today it relies on browser defaults).
- Contrast audit: fix text combos below WCAG AA (e.g. `bench-muted` on `bench-bg`, amber-on-amber).
- Type / spacing consistency nits.
- Files: `web/tailwind.config.ts`, `web/app/globals.css`, `components/{badges,home-leaderboard,
  run-axis-breakdown,score-bar,...}.tsx`.
- **Done =** tokens are single-source; no semantic colour hardcoded; visible focus on every
  interactive element; AA contrast on text; gate green.

### T2 — Home / leaderboard redesign
- Elevate the rig-match hero / first impression (the top fold).
- Leaderboard legibility: header clarity, rank/lane semantics, the UNRANKED-tier caveat, sort
  affordances.
- Responsive behaviour at sm/md.
- Files: `app/page.tsx`, `components/{rig-match-finder,rig-match-finder-row,rig-match-bounty,
  quality-bars,home-leaderboard,local-intelligence-index}.tsx`.
- **Done =** stronger first impression, clearer ranking story, no regressions; gate green.

### T3 — Inner pages pass
- methodology + trust: prose legibility, section anchors, scannability.
- compare: picker UX + delta-table clarity.
- model detail: quant ladder + scatter legibility.
- Files: `app/{methodology,trust,compare,model/[slug]}/page.tsx`, `components/{compare-picker,
  quant-decision-matrix,quality-vram-scatter,model-axis-profile,model-scatter,detail-grid,
  breadcrumbs}.tsx`.
- **Done =** each inner route reads cleanly + is consistent with the new tokens; gate green.

### T4 — Submit upload UI (+ dynamic Bounty)
- Real upload page: drag/drop or file-pick a run JSON; client-side validate against
  `lib/schemas.ts`; on valid, render a preview (composite, axes, manifest) reusing the existing
  run components; on invalid, show clear errors. Actual network upload **mocked** (clearly
  labelled) pending the Track-2 backend.
- Bounty sidebar: generate CLI commands from a config/data source instead of hardcoded strings.
- Files: `app/submit/page.tsx`, new `components/run-upload.tsx`, `components/rig-match-bounty.tsx`,
  reuse run/axis components.
- **Done =** a user can validate + preview their own run file locally; bounty is config-driven;
  gate green (incl. a vitest for the validator).

### T5 — Progress bar: CLI
- Instrument the runner to track per-item completion; render a TTY progress bar (gated to a TTY)
  with counts, tok/s, and ETA.
- Write an incremental `runs/{id}.progress.json` (`{state, items_done/total, current_bench,
  elapsed, eta, tok_s}`) during the run; finalise/remove it on completion.
- **Determinism:** the scored run JSON is unchanged; progress writes are side-channel only.
- Files: `cli/src/localbench/{orchestrate,runner,cli}.py`, a new progress module.
- **Done =** the bar shows on a mock / `--max-items` run; the final run JSON is byte-identical
  vs pre-change; CLI pytest green (incl. a determinism test + a progress-file test).

### T6 — Progress bar: web live-view
- Client component polling `/data/runs/{id}.progress.json` (dev-mode); renders progress + ETA on
  `/run/[runId]` when a run is in flight; falls back to the finished receipt when complete/absent.
- Must not interfere with the static finished-run view.
- Files: `app/run/[runId]/page.tsx`, new `components/run-progress.tsx`, a lib polling helper.
- **Done =** with a fixture progress JSON, the run page shows a live-updating bar in
  `npm run dev`; finished runs render as before; gate green.

## Resume note
If a session is lost: **this file + `git log` on `suite/v1-quant-wedge` are the durable state.**
Open the in-progress task's "**Done =**" criteria, re-run the gate, continue. Dev server:
`cd web && npm run dev` → http://localhost:3000 (if it 500s with a Tailwind `resolveChangedFiles`
ENOENT, clear the stale cache: `rm -rf web/.next web/node_modules/.cache`, then restart — see
`docs/SESSION-CHECKPOINT-2026-06-20.md`).

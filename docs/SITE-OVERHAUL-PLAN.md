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

## Tasks (priority order — foundation first)

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

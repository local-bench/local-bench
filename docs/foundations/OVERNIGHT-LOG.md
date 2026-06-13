# local-bench — Overnight Autonomous Log

*Newest entries at top. RUNNER: read this first to CONTINUE (not redo). Append, never overwrite.*

---

# ☀️ MORNING SUMMARY — 2026-06-14 (read me first)

**All authorized safe-scope work is DONE. Phase 1 + Phase 2 shipped. Stopped at the Phase-3 GATE as instructed (heroes need your eyes first).**

**Branch:** `site-overhaul` (off `foundations/suite-v1-research`). `main` untouched. 4 commits, all under `web/`:
`857361f` axis-agnostic refactor · `39c9f5c` tokens+fonts+SVG · `fbd4c20` index_version+copy · `7b3822b` AppShell+breadcrumbs+/submit.

**View it:** `cd web && npm run dev` → http://localhost:3000  (or `npm run build` for the static export).

**What's built:**
- **Axis-agnostic site** — the hardcoded mmlu_pro/ifeval/genmath set is gone; `web/lib/axis-config.ts` is the single source of truth. New benchmark axes now flow through schema→build_data→leaderboard→run pages with no code edits (missing axes render `n/a`). build_data output verified byte-identical to before.
- **Design system foundation** — 11 spec palette tokens in tailwind; chart SVG hexes are now token utilities; Inter + JetBrains Mono via `next/font` (tabular figures).
- **Versioning + honest copy** — `index_version` ("index-v0") in schema/data/pages; the stale `suite-v0` string and hardcoded axis names are gone (now data-driven).
- **Shell + structure** — persistent TopNav (brand + nav + `suite·index` stamp) on every page; breadcrumbs on model/run pages; new **`/submit`** stub with the real `localbench run` command + uploads-vs-local explainer.

**Gates (all green):** `npm run typecheck` · `npm test` 4/4 · `npm run build` (18 routes) · `npm run e2e` 8/8.

**Decisions I made (reversible — flag if you disagree):**
1. `index_version` value = **`index-v0`** (rename to index-v1 if you prefer).
2. Model page (`app/model/[slug]/page.tsx`) still hard-indexes `run.axes[axis]` — type-safe + runtime-safe, but NOT data-tolerant like the leaderboard. Left for the **Phase-3 model-page hero rework** (out of Phase-1a's file scope).

**What's LEFT (needs you / Track 2 — NOT done autonomously, per hard stops):**
- **Phase 3 heroes** — the Rig-Match finder, the "which quant?" decision matrix, `/compare`. Held for your review of the layout first.
- **Track 2 data** — discrimination probe + seeded quant-ladder runs (any GPU/spend needs you). Finder/matrix render placeholder until then.

**FYI:** `web/public/data/runs/` is gitignored (generated); regen refreshed slightly-stale composite CIs there — tracked data (index.json/models) unchanged except the new `index_version` line.

---

## PROGRESS — 2026-06-14 ~00:30–01:30 (os-backstop run) — PHASE 1 COMPLETE

Branch **`site-overhaul`** (off `foundations/suite-v1-research`). codex GPT-5.5 xhigh implemented; Claude reviewed every diff. View: `cd web && npm run dev`.

**Done (Phase 1 foundation), 3 commits:**
- `857361f` — **axis-agnostic refactor.** New `web/lib/axis-config.ts` is the single source of truth (`AXIS_CONFIG`/`AXIS_KEYS`/`axisLabel`/`isAxisKey`/`presentAxes`). `AxesSchema`→`z.record`; killed hardcoded mmlu_pro/ifeval/genmath in schemas, format, home-leaderboard (data-driven columns + sort, `n/a` cells), run page, run-axis-breakdown, build_data (`--benches` flag, weight-normalized composite). **Verified output byte-identical to prior generator.**
- `39c9f5c` — **11 design tokens** added to tailwind; **chart SVG hex → fill-/stroke- token utilities**; **next/font** (Inter + JetBrains Mono) wired, dropped platform font stack.
- `fbd4c20` — **index_version** ("index-v0") in schema+build_data+pages; killed stale `suite-v0` string (methodology now async-reads version); home axis copy now data-driven. Regenerated `public/data` — tracked model rows unchanged (only index.json gains the field).

**Gates:** `npm run typecheck` clean · `npm test` 4/4 · `next build` green (17 SSG pages) · new token utilities confirmed in built CSS.

**Notes for Michael:** (1) `index_version` value is `index-v0` — rename if you prefer index-v1. (2) `public/data/runs/` is gitignored (generated). (3) Model page `app/model/[slug]/page.tsx` still hard-indexes `run.axes[axis]` (type-safe, runtime-safe; out of 1a scope) — fold into the Phase 3 model-page hero rework. (4) Pre-existing: on-disk gitignored run files had slightly stale composite CIs vs current scoring lib; regen refreshed them — tracked data unaffected.

**NEXT:** Phase 2 — AppShell/TopNav + breadcrumbs (`layout.tsx`) + `/submit` stub. Then GATE: Michael reviews before Phase 3 heroes.

---

## STATUS — 2026-06-13 evening — LOOP ARMED, awaiting usage-limit reset

**Direction locked (Michael):** finder-first + prominent scatter, hybrid sequencing.
**Spec:** `docs/foundations/website-design-v2.md` (canonical). **Work order:** `docs/foundations/OVERNIGHT-AUTONOMY-PROMPT.md` (follow it exactly).
**Resume mechanism:** Windows Task `LocalBench-Overnight-Resume` (hourly, ~+3h..+13h, non-overlapping) → `C:\Users\Michael\.claude\resume-localbench.ps1` → headless `claude -p`.

**DONE:**
- 4-model design red-team (GPT-5.5 / Gemini 3.1 Pro / Qwen 3.7 Max / Opus) + synthesis — committed `549eef6`. Critiques in `redteam/`.
- Design spec v2 written (this is Task 0 — already done, skip it).

**NEXT (authorized safe scope — do in order, one codex task at a time, on branch `site-overhaul` off `foundations/suite-v1-research`):**
1. **Phase 1 foundation:** axis-agnostic refactor (kill hardcoded mmlu_pro/ifeval/genmath per `site-audit.md` §1.9; add `lib/axis-config.ts`) + 14 design tokens + `next/font` web fonts + stale-copy fixes + `index_version`.
2. **Phase 2 structure:** AppShell/TopNav + breadcrumbs (`layout.tsx`) + `/submit` stub.
- codex (GPT-5.5 xhigh, `--sandbox danger-full-access`) implements; review every diff; tests green; commit per task; refactor + quick review pass after each phase.

**HARD STOPS (do NOT):** build the finder/matrix HERO components (Phase 3 — needs Michael's eyes); run the discrimination probe / any anchor run / any spend / any GPU use; touch the vast box or 5090 mining; echo or commit API keys. If a step needs judgment, spends money, or tests fail twice → STOP, log here, wait for Michael.

**WHEN DONE:** write a MORNING SUMMARY at the top of this file (what's built, branch, `cd web && npm run dev`, what's left = heroes + Track 2), release `.loop-lock`, STOP (don't re-arm).
[2026-06-13T22:28:04] os-backstop launching headless claude
[2026-06-13T22:29:07] claude exited code=0
[2026-06-13T23:28:05] os-backstop launching headless claude
[2026-06-13T23:29:12] claude exited code=0
[2026-06-14T00:28:05] os-backstop launching headless claude

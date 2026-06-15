# local-bench — Overnight Autonomous Log

*Newest entries at top. RUNNER: read this first to CONTINUE (not redo). Append, never overwrite.*

---

# 2026-06-16 — SCORER FIT-FOR-PURPOSE FIX (the "27B ≈ frontier" mystery, solved)

**Michael's instinct was right — it was a scoring artifact.** Adversarial scorer red-team + grounding
in the actual run data found the local models' math "signal" was entirely false positives:
truncated non-answers (`finish_reason=length`) credited by the last-number fallback, plus
`math_verify` over-accepting numerically-different boxed answers. **Fixed + committed `29fb89e`**
(branch `suite/v1-quant-wedge`, cli/ scorers only; full suite **496 passed**).

**Measured impact (re-scoring stored runs):** math axis went from a fake tie to **~40% frontier vs
~0% local** — the discrimination it was hiding. Frontier essentially unchanged (GPT-5.5 40→40,
Gemini 50→40); locals' fake math collapsed to ~0. MCQ: only local truncation bold-FPs removed,
frontier untouched. **Full write-up: `docs/foundations/scorer-validation-2026-06-16.md`.**

**Branch state caution for whoever picks this up:** 9 branches; `suite/v1-scorers` +
`refactor/architecture` are already merged into `suite/v1-quant-wedge`. The working tree carries
UNCOMMITTED `web/public/data` + `docs/briefs` changes from the parallel `site-overhaul` refactor —
**left untouched**; the `29fb89e` commit staged only its 5 cli files. IFBench #2/#3 are NOT bugs
(faithful AI2 ports). Chance-correction #5 deferred (collides with site-overhaul's byte-identity gate).

**Still open before any re-run (bigger, need Michael):** (1) knowledge-axis content swap
SuperGPQA→MMLU-Pro (#53, ~36% bad keys); (2) reasoning-for-all lane re-run (GPU + per-lane cap
calibration). The scorer half of #54 is done; these two are not.

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

## PROGRESS — 2026-06-14 05:28 (os-backstop run) — NO-OP, all safe scope already complete

Woke, verified the lock (`os-backstop pid=75120`) was **my own** session's lock — traced it via the process tree: Task-Scheduler powershell 75120 → `claude.exe 23984` (the only Claude session started today; the lone "claude loop" from yesterday is a dead codex broker). Not a competing runner, so I proceeded.

**Found everything in authorized safe scope already DONE** (Task 0 spec + Phase 1 + Phase 2, 4 commits, HEAD `d60bbf0`). Did **not** redo anything. Confirmed: branch `site-overhaul`, `main` untouched, working tree clean except the wrapper's appended launch-log lines + out-of-scope untracked `own-benchmark-*` / `overnight-claude-output.log` (left alone — not mine).

**Re-verified the branch is green this morning:** `npm run typecheck` clean · `npm test` 4/4. (Skipped full build/e2e — code unchanged since the last run that verified them.)

**Phase 3 heroes remain the gate** (need Michael's eyes). Released `.loop-lock` and stopped; did not re-arm.

> **FYI Michael:** the hourly Task `LocalBench-Overnight-Resume` is still firing and will keep launching quick no-op runs until you disable it. Safe to turn off now that safe scope is complete.

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
[2026-06-14T01:52:04] claude exited code=0
[2026-06-14T02:28:05] os-backstop launching headless claude
[2026-06-14T02:29:56] claude exited code=0
[2026-06-14T03:28:05] os-backstop launching headless claude
[2026-06-14T03:29:22] claude exited code=0
[2026-06-14T04:28:05] os-backstop launching headless claude
[2026-06-14T04:29:09] claude exited code=0
[2026-06-14T05:28:05] os-backstop launching headless claude
[2026-06-14T05:35:31] claude exited code=0

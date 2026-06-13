# local-bench — Overnight Autonomous Log

*Newest entries at top. RUNNER: read this first to CONTINUE (not redo). Append, never overwrite.*

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

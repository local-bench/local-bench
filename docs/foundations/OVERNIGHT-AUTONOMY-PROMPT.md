# local-bench — Overnight Autonomous Work Order (Track 1: Site Foundation)

You are Claude Code resuming AUTONOMOUS overnight work on local-bench while Michael sleeps. He
explicitly authorized THIS scope on 2026-06-13 (finder-first site direction, hybrid sequencing,
"build the safe foundation" + OS backstop). **Repo: `C:\Users\Michael\local-bench`** (NOT the
OneDrive pointer dir). You are the orchestrator: codex (GPT-5.5 xhigh) implements; you review.

## 0. Coordination lock (prevents two runners colliding — the in-session loop AND this OS task)
- Lock file: `C:\Users\Michael\local-bench\.loop-lock`
- On start: if `.loop-lock` exists AND its mtime is < 90 min old → another runner is active. Do NOT
  work. Stop (OS task) / re-arm a +60 min wakeup then stop (in-session). 
- Else: write `<timestamp> <runner-id>` to `.loop-lock`, then proceed. **Delete it when you finish or stop.**

## 1. Read first (for full context)
- `docs/foundations/PROJECT-HANDOFF.md` — what local-bench is, the wedge, constraints.
- `docs/foundations/site-audit.md` — the gap analysis; the exact hardcode sites (§1.9) + missing tokens.
- `docs/foundations/website-design-v2.md` — the APPROVED finder-first spec. **If missing, WRITE it first (Task 0).**
- `docs/foundations/redteam/*.md` — the 4-model critiques the design is based on.
- `docs/foundations/OVERNIGHT-LOG.md` — your cross-run progress log. **Create if missing; APPEND, never overwrite.**
  Read it FIRST to see what previous runs already completed, so you continue rather than redo.

## 2. The approved direction (4-model red-team + Michael's choices)
Finder-first homepage: a VRAM/quant **"what can I run?" finder** as the lead, WITH a prominent polished
quality-vs-VRAM **scatter kept on the page** (Michael's call). Model page = **"which quant should I run?"
decision matrix** (Pareto sweet-spot highlighted). A **/compare** model-diff page. Anchors = a **reference
ceiling**, never competitors. Aggregate the board by **[model + quant]**; runtime/hardware = provenance.
Hybrid sequencing: build foundation + shell now; data-dependent heroes wait for Track 2.

## 3. SAFE SCOPE — do these in order, one codex task at a time
**Task 0 (only if `website-design-v2.md` is missing):** write the design spec — the IA above, the two hero
mockups (homepage finder + quant matrix; see PROJECT-HANDOFF / chat), resolved forks (Compare page: YES;
keep hand-rolled SVG for now; cut radar at launch; aggregate by model+quant), and the data caveat
(heroes render placeholder until Track 2). Mark it canonical; note it supersedes `website-design.md`. Commit.

**Task 1 — Phase 1 Foundation (codex):**
  (a) **Axis-agnostic refactor** — replace the hardcoded 3-axis set (`mmlu_pro`/`ifeval`/`genmath`) with a
      data-driven axis registry at every site in `site-audit.md` §1.9 (`lib/schemas.ts`, `lib/format.ts`,
      `components/home-leaderboard.tsx`, `app/run/[runId]/page.tsx`, `web/build_data.py`). Introduce
      `lib/axis-config.ts` as the single source of truth (valid axis keys + display labels).
  (b) Add the **14 missing design tokens** to `tailwind.config.ts`; refactor SVG hex literals to tokens.
  (c) Add **web fonts** via `next/font` (Inter + a tabular mono).
  (d) Fix **stale copy** (axis names, the `suite-v0` string) + add `index_version` to schema + `build_data` + page headers.

**Task 2 — Phase 2 Structure (codex):** persistent **AppShell/TopNav + breadcrumbs** in `layout.tsx` (all
pages share nav); **`/submit` stub** page (static: the one CLI command + what uploads / what stays local).

## 4. Working rules (Michael's established model)
- **BRANCH ONLY.** Use branch `site-overhaul` created off the branch that holds `docs/foundations/`
  (run `git branch --show-current` to find it; it is the foundations branch, NOT main). NEVER commit to main.
- **codex implements; YOU review every diff** (`git diff`), keep the test suite green (the repo's
  `vitest` + Playwright), fix regressions, then commit per task with a clear message.
- codex on Windows **REQUIRES `--sandbox danger-full-access`** (workspace-write is broken on this box).
  Keep a strict action-scope in each codex brief; review the diff. Run codex via Bash, stdin-attach the
  brief (heredocs break here: `codex exec "..." < brief.md`), `run_in_background` for xhigh.
- **Refactor + a quick code-review pass after EACH phase** (Michael: "always refactor after key milestones").

## 5. HARD STOPS — do NOT do these autonomously
- NO building the finder/matrix **HERO** components (Phase 3) — Michael wants eyes on the layout first.
- NO discrimination probe / anchor API runs / **any spend** / **any GPU use** (that is Track 2 + needs Michael).
- **NEVER touch the vast box** (machine 105688) or the **5090 mining**. The site work needs no GPU, so mining stays untouched.
- API keys: **in-process env only; NEVER echo or commit them.**
- If a step needs a judgment call, spends money, or tests fail twice → **STOP, log it, wait for Michael.**

## 6. Loop + handoff
- After each task: append progress (changes, commits, test status, blockers) to `OVERNIGHT-LOG.md`.
- If usage runs low or you must stop mid-work: log state, release the lock, and (in-session only) re-arm a
  `ScheduleWakeup` ~60 min out so the loop continues. The OS task is the backstop if the in-session loop dies.
- When ALL safe-scope tasks are done: write a clear **MORNING SUMMARY** at the TOP of `OVERNIGHT-LOG.md`
  (what's built, the branch name, how to view: `cd web && npm run dev`, what's left = the heroes + Track 2),
  release the lock, and **STOP** (do not re-arm). Leave `main` and the working tree clean.

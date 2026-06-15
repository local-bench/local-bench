# Overnight autonomous session — 2026-06-15 (for Michael's morning)

*Living doc; updated as milestones land. Discipline this session: commit locally, NEVER push;
no spend; no branch merges (that's #45, needs you); verify (tests/build green) before every commit.*

## TL;DR
- **Quant wedge COMPLETE** (the launch differentiator): full 5-rung Qwen3.6-27B ladder Q2→Q8. Flat
  plateau Q8→Q3, **measured cliff at Q2_K** (composite −5, CI excludes 0; deterministic axes drop 10–15).
  → run Q4_K_M/Q3_K_M, skip Q8/Q6, never Q2. Doc `docs/foundations/legB-quant-wedge.md`.
- **Discrimination probe SETTLED, $0 spent** (you flagged: check public data first). Public leaderboards
  already show weak→frontier spread on every axis → keep all 4 axes, provisional equal weights. Paid
  frontier-anchor LINES deferred to a launch-time decision. Doc `discrimination-probe-v1.md`.
- **Mining retired** per your note — 5090 is solely for local-bench now.

## Workstream status
| # | Task | State |
|---|---|---|
| #42/legB | Quant wedge (5 rungs) | ✅ done, committed (843e0a7) |
| #49 | Discrimination probe | ✅ done zero-spend, committed (61eb2fa) |
| #48 | Site v0→v1 migration + real quant data (codex, worktree `local-bench-site`) | ⏳ codex running; build passes + 55 routes prerendered; doing visual QA |
| #50 | Backlog model: Gemma 4-12B-it Q4_K_M on suite-v1 | ⏳ running on 5090 (answer-only, N=80) |
| #51 | Wire per-axis composite (math=1 axis not 2 benches) | pending — do after site lands (match site's weighting) |
| #46 | This handoff | ⏳ living |

## Decisions waiting on you
1. **Frontier anchor spend** — discrimination needed none. But the *comparison-chart* anchor lines
   (current frontier on our exact subset) would cost ~$10–15. Deferred; recommend citing public
   "reported" numbers first, spend only if anchor lines become the launch's load-bearing visual.
2. **#45 scoring-lineage branch reconciliation** — still needs you (branches diverged: main /
   suite/v1-* / site-overhaul / quant-scoring-fixes / foundations/suite-v1-research).
3. **Rotate API keys** (a 06-14 transcript grep leaked them) — still outstanding.

## Branches (fragmented — eventual reconcile is #45)
- `suite/v1-quant-wedge` (my work this session): wedge + probe + backlog docs.
- `site-overhaul`: the web app; codex migrating it on worktree `C:/Users/Michael/local-bench-site`.
- `main`, `suite/v1-scorers`, `quant-scoring-fixes`, `foundations/suite-v1-research`, `refactor/architecture`.

## How to verify / run (Windows)
- Tests: `cli\.venv\Scripts\python.exe -m pytest cli/tests -q` (currently **468 passed**).
- Serve a local GGUF (5090, WSL): `~/bin/micromamba run -n cuda ~/llama.cpp/build/bin/llama-server -m ~/models/<gguf> -ngl 99 -c 8192 --parallel 2 --jinja --host 127.0.0.1 --port 8080` (+`--reasoning-effort none --max-tokens 2048` on the localbench run for answer-only).
- Site: worktree `local-bench-site`, `cd web && npm run build` / `npm run dev`.
- Real runs in `runs/` (gitignored): lcpp-q{2_k,3_k_m,4_k_m,6_k,8_0}.json + gemma-4-12b-it-q4_k_m.json.

## Remaining task list (autonomous plan for the night)
- After site lands: review diff + verify → **refactor pass** (per your standing instruction) → then #51.
- Next suite axes toward the 7-axis adopt set: **#40 RULER long-context**, **#39 LCB output-prediction** (codex builds, serialized after site). Refactor after each.
- Fallback if list runs dry: QA testing (full suite + site e2e + a code-review pass).

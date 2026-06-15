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

---
## Progress update (~19:55)
- **#48 site migration DONE + verified** (codex e942eb6) and **#50 Gemma DONE + added to site** (0c19d0f) — both on `site-overhaul`, build green, NOT pushed.
- **Refactor pass running** (codex, behavior-preserving cleanup of the migration) per the "refactor after every milestone" rule.
- **#51 (per-axis composite) — DEFERRED to you, deliberately.** The CLI composite is per-*bench* equal (math axis = 40%, 2 benches) → legB composites ~41. The site now uses per-*axis* equal (math = 25%) → ~50. The wedge conclusion (flat Q8→Q3, cliff Q2) is identical under both; only absolute composite numbers shift. Reconciling means re-stating the legB launch doc's numbers + touching composite() AND paired_delta — an editorial methodology call I'd rather you make than do unsupervised. Flagged, not actioned.
- **#13 (IFEval parity) looks superseded by #38 (IFBench parity)** — IFEval is v0-only, not in suite-v1. Recommend closing.
- Tests green (468). Next autonomous steps: review codex refactor when it lands → then a suite axis (#40 RULER or #39 LCB) via codex, or a QA pass.

---
## SITE MILESTONE COMPLETE (~20:10) + the key decision for you

**Site (site-overhaul) is done & green** — 4 commits, NOT pushed:
`e942eb6` migrate to suite-v1 axes · `0c19d0f` add Gemma real run · `c32e8f9` refactor (behavior-preserving; public/data byte-identical) · `8420f15` port web-data test to v1 (3 passed). `npm run build` green throughout.

### 👉 RECOMMENDED FIRST ACTION: reconcile the branches (#45) before building more axes
The branches have diverged and it's now the bottleneck:
- `suite/v1-quant-wedge` (my work): the suite-v1 **scorers** + wedge + probe — **468 tests pass**.
- `site-overhaul` (codex's work tonight): the **site** migrated to suite-v1 — but its cli/ predates the scorer work (**only ~173 tests**).
- Codex saw 4 failures in site-overhaul's full suite: 3× `test_genmath_private` hash + 1× `test_ifeval` (`langdetect unavailable`). **These are NOT regressions** — I verified the same tests **pass (18/18) on suite/v1-quant-wedge**. They're stale-branch + a missing dep in codex's throwaway env.
- **So nothing is broken; the branches just need merging onto one base.** Building #39/#40 now would add more divergence. Recommend: reconcile first (your call on lineage/order), then build remaining axes on the unified base.

### Ready to build once reconciled (teed up, not started — additive, not launch-blocking)
- **#39 LCB output-prediction** (exec-free; contained axis like supergpqa/bfcl).
- **#40 RULER long-context** (needs a generator + truncation assertion + long-ctx serving; ties to your 8k/32k/128k interest — you may want to steer its approach).

### Your-call items (flagged, not actioned)
- **#51 per-axis composite** — CLI is per-bench (math 40%), site is per-axis (math 25%); reconcile + re-state legB. Editorial.
- **#45 branch reconciliation** (above). · **Rotate API keys** (06-14 leak).

### Done tonight
Quant wedge (5 rungs, cliff at Q2) · discrimination probe (zero-spend, public data) · site→suite-v1 + Gemma + refactor + test-port · mining retired. Locally committed, nothing pushed.

---
## QA spot-check (scoring core) + loop status
- Chance-correction `signed_score=(raw−chance)/(1−chance)` is CORRECT (no inference clamping; display clamp is cosmetic). Verified: supergpqa raw 0.50 @ chance 0.10 → 0.444 = reported. Scoring methodology was already GPT-5.5 red-teamed (per plan).
- Minor observation (not a bug; moot at 0 errors): infra-errored items count as incorrect in raw_accuracy. Fine as policy; revisit only if error rates rise.
- `suite/v1-quant-wedge`: **468 tests pass.**
- **Loop status:** launch-critical work done + refactored + QA-checked; everything green, nothing pushed. Remaining tasks need your call (#45 reconcile, #51 composite) or are best built post-reconcile (#39 LCB, #40 RULER). Holding off on more divergent branch work — winding to a quiet idle, will resume on your word.

---
## Final QA: site e2e GREEN (~21:02)
Playwright e2e on site-overhaul: **12/12 passed** (55s) — all routes incl. real `qwen3-6-27b` model page + matrix/scatter, run detail `qwen3-6-27b__lcpp-q8_0`, compare, leaderboard (deterministic sort). Full QA matrix now green: cli 468 · web vitest 17 · e2e 12 · `npm run build` · scoring core verified.

**Loop ended here — genuine idle.** All launch-critical work done, refactored, QA-verified, handed off; nothing pushed. Resume points for you, in priority order: (1) **#45 reconcile branches** (the unblocker), (2) **#51 composite weighting** (your call), (3) build **#39 LCB / #40 RULER** on the unified base, (4) rotate API keys. Re-engage me anytime.

---
## "Do all" execution (2026-06-16) — #45, #51 DONE; #39 building; #40 next
- **#45 RECONCILE — DONE.** All six branches now merge into `suite/v1-quant-wedge` (the unified branch):
  main, suite/v1-scorers, quant-scoring-fixes (hardened scoring was already in-content), refactor/architecture,
  site-overhaul, foundations/suite-v1-research. The "fragmentation" was disjoint parallel branches (wedge =
  cli/suite/docs, site = web/) → conflict-free merges. The hardened-scoring (cluster-robust/FDR/McNemar) content
  was already present. 468 tests green; site data byte-identical; site e2e 12/12. **The old feature branches can
  now be deleted** (all `--merged`). NOT pushed.
- **#51 PER-AXIS COMPOSITE — DONE** (commits 6419a9c + a4e87ae). composite() + paired_delta both group benches
  into the 4 axes via BENCH_DOMAINS (Math = olymmath_hard+amo pooled). CLI now == site exactly (Q4 0.499 …).
  suite.json weights 0.25. legB + discrimination docs re-stated (cliff now −6.0..−6.7, conclusion identical).
  v0 preserved via weight-normalization. 468 green.
- **#39 LCB CODING AXIS — building** (codex bj1uobbcf, branch feat/coding-axis off the unified base): exec-free
  Test-Output-Prediction, CC-BY-4.0, mirrors the bfcl bench. New axes are additive — DOMAIN_WEIGHTS normalizes
  over axes present, so existing 4-axis wedge runs are unaffected. ON DONE: review + merge to unified base.
- **#40 RULER long-context — NEXT (bigger).** Synthetic generator @32k + a serving-truncation assertion +
  LongBench-v2. More infra than #39; ties to the context-tier wedge (#47) you had interest in steering.
- Pre-existing working-tree cruft remains (modified OVERNIGHT-LOG/PROJECT-HANDOFF/README + web/public/data
  line-ending churn) — not mine to discard; flagged for your triage.

---
## ACTION ITEM (Michael, 2026-06-16): hardware recording
- **Already captured** in the run manifest: `manifest.hardware` records GPU name + VRAM + driver + CPU + OS
  (e.g. "NVIDIA GeForce RTX 5090", 32607 MB, driver 596.36, Windows-11). So basic recording is DONE.
- **TODO (action later):** (a) verify cross-platform detection — Mac M-series (Metal/MPS, "Apple M5", unified
  memory), AMD GPUs, and CPU-only rigs (the current probe is NVIDIA/`nvidia-smi`-centric); (b) **surface
  hardware on the site** (run + model pages should show "ran on RTX 5090 / Mac M5 / …") — it's in the manifest
  but not yet displayed; (c) include it in the manifest identity/canonicality + a hardware facet/filter.

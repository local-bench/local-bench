# SESSION HANDOFF — 2026-06-14 (quant red-team + scoring fixes)

*For the main/coordinating agent picking this up. Written after a runaway-agent incident (see §0).
Author: the bench-design session. Nothing below is lost — recovery info in §1.*

---

## ★ DIRECTIVE — COMPLETE THIS WORK (authorised by Michael, 2026-06-14)
**The main agent is authorised and instructed to drive the scoring-fix work to completion — do NOT hand
back for step-by-step approval.** Execute §3 end-to-end:
1. **Verify** codex's 3 fixes in an **isolated `git worktree`** (§3.1) — run the 14 scoring tests + live-probe
   the three properties (absent-cluster identity, shared-cluster widens CI, BH suppresses noise / keeps a real
   regression). Also finish the diff review of `bootstrap.py` / `paired_delta.py` / `subgroups.py`.
2. **Refactor** the now-correct scoring code (§3.2); keep all tests green.
3. **Cherry-pick the 3 cli-only commits onto `main`** (§3.3) → merge once tests pass (PR optional, solo repo).
   **Scoring fixes ONLY — do NOT promote the web/docs stack.**
4. **Commit the session docs** to the `foundations/suite-v1-research` lineage (§3.4).

**Drive to DONE.** Stop and surface ONLY if: a test fails twice and the cause isn't obvious, a cherry-pick
conflicts, or the working tree is still being mutated by stray agents (re-check `HEAD` first — §0).

**Guardrails (standing):** work on branches; never force-push or skip hooks (`--no-verify`); all tests pass
before merge; never echo/commit API keys; the vast.ai box (105688) + RTX 5090 mining are EXCLUDED from any run.

**NOT part of "this work" — still Michael's call, do NOT action:** the §4 strategic sign-offs — approving
adopt-only, **authorising the discrimination probe or ANY GPU/API spend**, the exec stance, the refresh cadence.
The scoring fixes are correctness fixes that are independent of those; complete them without running the probe
or spending anything.

## 0. Workspace incident (READ FIRST)
A runaway fleet of autonomous sessions (**24 `claude.exe` + 17 `codex.exe`** at peak) was spawned by an
hourly scheduled task whose non-overlap guard had failed. They were checking out branches and committing
into the **shared working tree** concurrently — HEAD bounced quant-scoring-fixes ⇄ site-overhaul and
foreign web commits (`112e9b4`, `62c4343`, `a17b531`) landed mid-session (one transiently onto
`quant-scoring-fixes`). **Fixed:** disabled BOTH `\LocalBench Resume Reminder` (was Ready/firing — the
culprit) and `\LocalBench-Overnight-Resume`. No new sessions will spawn; running ones wind down on their own.
**Do not trust the working-tree checkout state without re-checking `git -C <repo> rev-parse --abbrev-ref HEAD`
first** — and prefer an **isolated `git worktree`** for any verify/test/merge so you never fight the shared tree.

## 1. Recovery / where things live (immutable)
- **codex's scoring fixes** = 3 commits on branch **`quant-scoring-fixes`** (tip `e343fee81…`), recoverable by SHA even if a ref moves:
  - `7b84210` cluster-robust block bootstrap · `9a62c4a` FDR + exact-McNemar on severe-regression flag · `e343fee` chance-corrected-delta invariant test.
- **Uncommitted session docs** are in the shared working tree AND backed up outside the repo at
  `C:\Users\Michael\AppData\Local\Temp\lb-docs-backup\` (foundations/ + briefs/ + `tracked-doc-edits.patch`).

## 2. What this session accomplished
1. **`suite-v1-DECISION.md`** (new, in `docs/foundations/`) — the decision that **closes bench-design**:
   adopt-only v1 (frozen 7-axis candidate set), own-bench (StateTrace+ConstraintForge) **ring-fenced** as
   run-when-idle R&D, and a **two-leg discrimination probe** (A between-model, B within-model quant).
   README + PROJECT-HANDOFF pointers updated to it. *(All uncommitted.)*
2. **Quant-degradation wedge red-team** — 3 frontier models (GPT-5.5 REVISE / Gemini 3.1 Pro FATAL / Qwen
   3.7 Max REVISE) attacked the paired-delta measurement + Leg B. Architecture sound; validation was
   underpowered. Synthesis `quant-methodology-redteam.md` + raw verdicts in `redteam/{gpt55,gemini,qwen}-quant-review.json`.
   Fixes folded into DECISION §3 (Leg B rewrite: multi-model×runtime matrix, Standard-tier+ N w/ MDE +
   equivalence margin, per-config N≥10 floor, format-vs-capability split, gate raised) and §4 (3 code fixes).
3. **codex implemented the 3 code fixes** (§1) on `quant-scoring-fixes`. **Verified correct so far (read-only,
   from refs):** `signed_score.signed_delta` unchanged (correct `d/(1−c)` form) + docstring; `metadata.cluster_for_item`
   correct (absent `cluster` ⇒ item id ⇒ singleton ⇒ backward-compatible); all 4 new tests present
   (`...clusters_are_absent_matches_explicit_singletons`, `...items_share_cluster_uses_block_resampling`,
   `...noisy_subgroup_regressions_are_bh_suppressed`, `...signed_delta...matches_aggregate_score_difference`);
   codex's "14 passed" was real. **NOTE:** an earlier "codex misreported / tests missing" alarm was a FALSE
   ALARM caused by the concurrency (was reading the site-overhaul baseline tree). codex did its job.

## 3. What's LEFT (the next agent's to-do, in order)
1. **VERIFY codex's fixes in an isolated worktree** (don't touch the shared tree):
   `git -C C:/Users/Michael/local-bench worktree add ../lb-verify quant-scoring-fixes` →
   `cd ../lb-verify/cli && .venv/Scripts/python.exe -m pytest -q tests/test_scoring_v1.py tests/test_scoring_aggregate.py`
   (expect **14 passed**). Then **live-probe** the 3 properties on synthetic runs: (a) absent-cluster output is
   byte-identical to before; (b) shared-cluster items WIDEN the CI; (c) BH suppresses noisy small regressions
   but still flags a real all-flip regression. *(Still review bootstrap.py / paired_delta.py / subgroups.py
   diffs — the cluster block-resampling + exact-McNemar/BH math — which I had not finished when the incident hit.)*
2. **Refactor pass** (user requested "fixes then refactor") on the now-correct scoring code.
3. **Cherry-pick the 3 verified scoring commits onto `main`** — they touch only `cli/` and are independent of the
   docs/web stack. `git checkout main && git checkout -b fix/scoring-redteam && git cherry-pick 7b84210 9a62c4a e343fee`
   → tests → PR → merge. **Do NOT merge `quant-scoring-fixes` wholesale** — it sits on a 16-commit stack
   (foundations docs → site-overhaul web → scoring) none of which is on main yet; that would drag the unreviewed
   web + docs onto main.
4. **Commit the session docs** to the `foundations/suite-v1-research` lineage once the tree is quiesced.

## 4. Open decisions (need Michael)
- **Merge scope:** just the scoring fixes to main (recommended), or promote the web + docs stacks too?
- **DECISION §5 sign-off** (unchanged): approve adopt-only; authorise the discrimination probe (~$5-15 + 5090,
  now with Leg B); exec stance (exec-free coding at launch); refresh cadence.

## 5. Security
Earlier in-session a `grep` accidentally printed **Claude / Google / OpenAI** key VALUES to the transcript
(Qwen/DashScope NOT exposed). **Recommend rotating those three keys.** Keys live in `Desktop\API keys.txt`
(in-process use only, never echo/commit).

## 6. Branch map (as of handoff)
`main` (clean, no foundations docs) → `foundations/suite-v1-research` (+5 docs) → `site-overhaul` (+web overhaul,
actively advanced by the fleet: quality-bars, rig-match tiers) → `quant-scoring-fixes` (+codex's 3 scoring fixes).
`refactor/architecture` = even with main.

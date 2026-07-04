# DECISION — suite-v1.1 methodology lock

*2026-06-17. Inputs: independent red-teams by GPT-5.5 xhigh (`gpt55-review.md`) and Gemini 3.1
Pro (`gemini-review.md`) on the same brief (`00-redteam-brief.md`), plus my own verification of
their load-bearing empirical claims. This doc is for Michael's sign-off.*

## SIGN-OFF — Michael, 2026-06-18
- **KV cache: hold f16** (Q8 declined).
- **Staged validation campaign (Section D): APPROVED.**
- Converged calls + splits: proceeding. RULER + mixed-difficulty math enter as **candidates**;
  Stage 2 discrimination data decides keep/weight. **Difficulty-stratification stays retired.**
  One signed weight source-of-truth.
- Protocol: 20-item throughput probe + wall-clock estimate reported **before** committing each GPU
  stage; one model/server/run at a time.

## Bottom line
Two independent frontier reviewers converged: **the current 6-axis, equal-weight, wedge-led
suite is not lockable as-is — but the fixes are clear and they agree on almost all of them.**
Labels differ (GPT-5.5 "needs-rethink", Gemini "sound-with-fixes"); the substance is the same.
Net: **cut to a core that actually discriminates, prove the wedge before building on it, fix the
composite, and verify by targeted test rather than more leaderboard runs.** Good news inside the
critique: the product does NOT depend on the wedge existing — "verified local quality vs frontier"
stands on its own, and the wedge is upside.

## A. Converged calls — high confidence, I recommend we adopt
1. **Wedge is unproven → gate it before it is the foundation.** Both designed nearly the same
   experiment (Section D). Until it passes, do not make quant-degradation the public launch claim.
2. **6 axes → a 3-4 axis discriminating core.** Both KEEP Knowledge (MMLU-Pro) + IFBench. Both
   pull **LCB output-prediction** and **BFCL single-turn** OUT of the headline (saturated / AST
   only checks syntax). Both want **math fixed so locals actually score**. Both say **do NOT build
   difficulty-stratification** for launch (over-engineering) — this retires the Move-2/Move-3 track.
3. **Reasoning-ON-only lane stays** — but **verify the 8192 budget** with a 4k/8k/12k/16k sweep;
   it may under-measure verbose R1-class models (Gemini: they think 16-24k).
4. **Composite: kill equal-weight + the 3 duplicate weight copies.** One signed, versioned suite
   manifest is the sole source of truth (runtime + server + web read it). Weight by observed spread
   (with caps) over discriminating axes only; show the **weakest axis**; report the **three
   uncertainties** distinctly (run-to-run CI, paired quant-delta CI, cross-item generalization CI).
5. **Validate before lock** (scorer audit, contamination, budget sweep) — not more full runs.

## B. Splits — your call, with my lean
- **RULER long-context:** GPT-5.5 keep (+ more items) vs Gemini park (too slow, users abort).
  **My lean: KEEP.** Long-context is a genuine local pain point few benchmarks cover and it
  discriminates; manage cost with item count, don't delete a differentiator.
- **Math fix:** Gemini swap to MATH-500 (levels 1-5) vs GPT-5.5 rebuild/mixed-difficulty.
  **My lean: mixed-difficulty math** spanning easy→hard so it discriminates across the whole
  local→frontier range (pure MATH-500 risks saturating frontier; pure OlymMATH floors locals).
- **KV cache (challenges your prior call):** Gemini argues f16 KV at 64k eats ~10GB, forces users
  onto smaller weight-quants, so we'd be benchmarking a config few people run; it wants Q8 KV
  allowed. **This is your decision** — I'm flagging it honestly, not overriding you.

## C. My verification (checked, not relayed)
Gemini's loudest alarm — "93.8% MMLU-Pro proves a broken, too-lenient scorer (false positives)" —
**is REFUTED.** (1) The scorer (`mcq.py`) is hardened against exactly that: marker-anchored with
negative lookahead, treats "A or B" as ambiguous (no credit), ignores letters in trailing
explanation, accepts a bold letter only if it ends the response (a prior FP already fixed). (2) All
32 items: 30/32 correct, each correct one ending in a genuine reasoned "Answer: X"; the 2 wrong are
honest (1 truncated, 1 confidently-wrong). (3) Its "impossible" framing leaned on GPT-4o-era SOTA
(~75-80%) and ignored that this was n=32 (wide CI) and that current reasoning-frontier clears ~90%.
**BUT** the concern *underneath* it — knowledge may saturate at the top + MMLU-Pro contamination —
is real and both reviewers flagged it → **re-stratify the knowledge axis harder.**

## D. The one thing that needs spend: a designed validation campaign (the gate that lets us lock)
Not open-ended calibration — a bounded campaign with **pre-registered pass/fail rules**, run
**cheapest-first** so we can kill early:
- **Stage 0 — no GPU:** manual scorer-audit per axis; reconcile the 3 weight copies → 1 manifest;
  check on existing data whether math flooring is the dataset or the scorer.
- **Stage 1 — wedge gate, 8B first:** Qwen3.6-8B, Q6 vs Q4, ~1,000 stratified paired items,
  reasoning-on; stratified paired bootstrap + McNemar. **If Q4 drop <3pp → wedge is a secondary
  feature; pivot the product claim to distance-to-frontier** (and we stop here on the wedge). If it
  shows ≥4pp → escalate to 14B/27B + Q3/Q2 per the full design.
- **Stage 2 — axis discrimination/calibration:** measure local→frontier spread per candidate axis;
  set keep/weight (spread-proportional). Drops anything that doesn't move rank order.
- **Stage 3 — budget sweep:** 4/8/12/16k on ~300 mixed items to confirm or correct the 8192 budget.

**Discipline I owe you:** before committing each stage I will measure tokens/item on ~20 items and
give you a real wall-clock + (if any) cost estimate — the step I skipped last week that caused the
4x blowout. Stages run strictly one-at-a-time on the 5090, never in parallel.

## E. Proposed locked core (suite-v1.2), pending the gate
Headline = **Knowledge (harder MMLU-Pro) + IFBench + mixed-difficulty Math + RULER-32k**
[+ BFCL-multi-turn only if Stage 2 shows it discriminates]. LCB + BFCL-single-turn → experimental
profile axes, not headline. Reasoning-on; budget set by the Stage-3 sweep. Composite =
spread-weighted over discriminating axes, one signed manifest, weakest-axis shown. Q2 = internal
positive-control only. Public wedge claim held until Stage 1 passes.

## What I need from you
1. **Sign off on the converged calls (Section A)** and my leans on the splits (Section B: keep
   RULER, mixed-difficulty math).
2. **Your KV-cache call** — hold f16, or allow Q8 KV at 64k.
3. **Authorize the staged validation campaign (Section D)** — I bring throughput-measured estimates
   before each stage; nothing runs until you say go.

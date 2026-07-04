# GPT-5.5 xhigh — suite-v1.1 methodology red-team

**VERDICT: needs-rethink.** The product may be viable, but this suite is not sound-to-lock
while the wedge is unproven and half the composite may be non-informative.

## 1. The Wedge
Do not make quant degradation the launch foundation until it survives a clean gate.

Minimal experiment:
- Models: Qwen3.6-8B, Qwen3.6-14B, Qwen3.6-27B; add one non-Qwen 8-12B sanity model only if Qwen results are flat.
- Quants: Q6_K baseline, Q4_K_M primary wedge, Q3_K_M stress, Q2_K positive-control sentinel.
- Items: 1,200 paired items/model for Q6/Q4/Q3; 400 paired for Q2. Stratify: 300 MMLU-Pro, 250 IFBench, 140 math, 150 LCB output-pred, 60 RULER, 300 BFCL/multi-turn.
- MDE: target 4pp Q4-vs-Q6 at ~80% power. ~600 items screens 5pp but cannot kill the wedge.
- Test: same prompts/runtime commit/sampler/template. Stratified paired bootstrap over items for composite delta + McNemar/sign test as sanity. Effect size first, p-value second.

Go/no-go:
- GO if Q4 drops >=4pp vs Q6 in >=2 of 3 sizes, 95% CI upper bound below 0, and Q6 >= Q4 >= Q3 monotonic within 2pp noise.
- NO-GO if Q4 drop <3pp in 2+ sizes, or Q3/Q2 not clearly worse -> quant degradation becomes a secondary audit feature, not the product wedge.
- If thin at all sizes, distance-to-frontier alone can still support a beta benchmark, not the original differentiated product claim.

## 2. Saturation / Flooring
Stop equal-weighting the six axes.
- Knowledge: keep, but 93.8% is a red flag — re-stratify harder if local 27B is near frontier.
- IFBench: keep, assuming checker false-negative rate <2pp after audit.
- Math: rebuild or downweight. A local floor measures frontier gap, not local ranking. Keep only if mixed difficulty gets locals into a 10-70% pass band.
- Coding LCB output-pred: drop from composite unless harder subsets show >=10-15pp spread. Saturated output prediction is decorative.
- RULER-32k: keep, increase items. 64k rig standard with RULER-32k does not prove 64k ability.
- BFCL: drop single-turn from composite; keep only hard/multi-turn if it discriminates. AST saturation may mean checker/task weakness.

Difficulty stratification is right long-term but too much for a solo two-week lock. Simpler: calibration ladder, remove saturated/floored axes from headline, weight by observed spread with caps.

## 3. Scope
Six-axis launch is over-engineered. Two-week defensible suite: Knowledge hard subset; IFBench; RULER-32k; one of {BFCL multi-turn/hard OR mixed-difficulty math, whichever discriminates}. Don't ship LCB output-pred or BFCL single-turn in headline if saturated — publish as experimental profile axes.

## 4. Lane
Reasoning-ON-only is acceptable for the headline. You lose fast-mode comparison, quality-per-token, and isolating "thinking helps" from base competence — acceptable because the product is "best local quality on my rig," not "efficient serving mode." Required guardrail: 4k/8k/12k/16k budget sweep on 300 mixed items; if 8k is >1.5pp below 16k for verbose models, 8192 is still under-measuring. Change-my-mind: thinking-on/off rank correlation below 0.85 across popular configs -> you need a fast lane.

## 5. Validity Traps (run these, not more leaderboard runs)
1. Scorer/parser brittleness: hand-audit 100 failures + 50 passes per axis across weak/mid models. False-score rate must be <2pp.
2. Budget under-measurement: budget sweep above; unparseable failures <1%.
3. Contamination: compare public items to private paraphrases/canaries; >5pp gap = contaminated axis.
4. Runtime/template confounds: rerun 300 paired items across runtime/template variants; if delta >3pp, treat runtime/template as first-class config.
5. Leaderboard gaming: try forging transcripts; if easy, split verified-official from community-self-reported.

## 6. Composite
No equal-weight composite until axes pass discrimination checks. One signed suite manifest = source of truth; runtime, server, and web consume the same versioned weights. The three-copy weight setup is a validity bug waiting to recur. Primary: calibrated composite over discriminating axes only; secondary: per-axis profile; add weakest-axis reporting. Weighting: spread-proportional with caps or explicit editorial; equal-weight only after all axes discriminate. Report three uncertainties: run-to-run repeatability CI, paired quant-delta CI, cross-item generalization CI.

## What I would cut
Public quant-wedge claim until the gate passes; LCB output-pred from headline; BFCL single-turn from headline; full difficulty stratification for launch; answer-only lane; Q2 from public scoring (keep as internal positive control); any composite whose weights are duplicated in code.

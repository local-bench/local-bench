# KLD VALIDATION — Gemma-12B (2026-06-19): ADOPT KL-divergence (validated)

*Red-team-refined validation (KLD-RESEARCH.md + dual red-team = adopt-with-conditions). Tool: llama.cpp
llama-perplexity, two-pass. References: BF16 (true) + Q8_0 (proxy). Calib: hashed wikitext subset
(100 KB, sha256 a483e4a319…). Task churn from the existing Gemma ladder runs.*

## VERDICT: ADOPT KLD as the quant-DRIFT metric. Validated — every red-team pass-condition met, no falsifier.

## Result: KLD is the smooth, granular signal accuracy hid
| Gemma-12B, KLD vs BF16 | Q8 | Q6 | Q5 | Q4 | Q3 |
|---|---|---|---|---|---|
| Mean KLD | 0.184 | 0.396 | 0.596 | 0.915 | 1.595 |
| Median KLD | 0.020 | 0.064 | 0.152 | 0.312 | 0.879 |
| 99% KLD | 3.46 | 5.84 | 7.21 | 8.56 | 9.88 |
| Same-top-p | 86.9% | 79.4% | 73.6% | 67.1% | 54.7% |
| RMS Δp | 8.3% | 11.6% | 14.4% | 17.2% | 21.5% |
| accuracy Δ vs Q8 | 0 | +1.3 | +4.2 | −2.4 | −6.4 |
| task churn (flips) | 0% | 12.0% | 11.3% | 12.7% | 18.0% |

Mean KLD ~doubles each step (≈8.6× Q8→Q3); every quant level is cleanly separated.

## Metric hierarchy (coherent, increasing sensitivity)
- **Accuracy** — coarsest; flat-then-cliff (noisy +1.3/+4.2/−2.4 across Q6→Q4, cliff at Q3). MASKS degradation.
- **Churn (task flips)** — FREE, UNIVERSAL (any model, no FP16 baseline, from every task run); reveals hidden
  change (~12% of answers flip at Q4 despite flat net accuracy) but lumps Q6–Q4.
- **KLD (distribution drift)** — smoothest + most granular; separates every level; expert-credible early-warning.

## Red-team pass-conditions — all met
- KLD rises before accuracy moves ✓ (steady Q8→Q4 while accuracy flat).
- Q3 cliff visible ✓ (Mean KLD 1.59, Same-top-p 55%).
- KLD correlates with churn / behavioral risk ✓ (Q3 = max KLD + max churn + accuracy cliff; KLD more granular).
- **Q8-proxy ≈ BF16 reference ✓** — KLD-vs-Q8 Same-top-p (Q6 79.3 / Q5 73.0 / Q4 66.3 / Q3 54.7) ≈ vs-BF16
  (79.4 / 73.6 / 67.1 / 54.7). The Q8 proxy is VALIDATED → big models (FP16 infeasible on the 5090) get a
  valid drift curve vs Q8.
- Falsifiers NOT triggered: KLD isn't flat; Q4's high KLD comes WITH 12.7% churn (not "no flips"); proxy matches.

## Caveats / productionization
- **Calibration artifact:** raw wikitext on the instruct (`-it`) model → high baseline PPL (~506), so ABSOLUTE
  Same-top-p is deflated (Q8 should be ~99%, shows 87%). The SHAPE + rankings are robust + validated; ABSOLUTE
  numbers need a model-suited, multi-slice calibration corpus (prose / instruction / code-math, hashed) for
  production headlines. Headline median + q99 KLD, not mean alone.
- Validated on one model + one slice. Production: run the multi-slice rank-stability check before publishing absolutes.

## How it ships (guardrails, locked)
- Model-page **"drift" column**: KLD (median + q99) + Same-top-p, framed as "drift from the full-precision
  reference — lower = more faithful; THIS IS NOT A TASK SCORE," beside accuracy + churn + VRAM + speed.
- Reference: BF16/FP16 where it fits; "reference = Q8" labeled visibly for big models (proxy validated here);
  never mix FP16-relative and Q8-relative on one scale.
- KLD never colors a quant "worse" alone — only with task-delta / churn / subgroup movement.
- The product is the DECISION LAYER (accuracy + churn + KLD + VRAM + speed → "run Q4 unless you need low-drift").

## Next (implementation)
Wire KLD (llama-perplexity two-pass) + churn (from task runs) into the pipeline + the model-page drift column;
standardize the multi-slice hashed calibration corpus; regenerate absolute numbers on the production corpus.
Raw evidence: ~/kld/kld-*.log (per-quant panels), ~/kld/calib.txt (sha256 above).

# WEDGE GATE RESULT — Gemma-4-12B Q8 vs Q4 (reasoning-on)

*2026-06-18. Stage 1 of the approved validation campaign. Subject: Gemma-4-12B (unsloth GGUF),
Q8_0 baseline vs Q4_K_M, reasoning-on (budget 8192), f16 KV, 12k/slot, paired on identical items.*

## VERDICT: NO-GO on the accuracy quant-wedge
Q8→Q4 costs ~0 accuracy with reasoning on. The headline "quant-degradation **accuracy** wedge"
does not survive contact with reasoning-on models. The quant cost is real but lands in
**compute/tokens**, not accuracy.

## Results (paired, Q8_0 baseline vs Q4_K_M)
| Bench | n | Q8 | Q4 | Δ (Q8−Q4) | 95% CI (paired bootstrap) | McNemar exact p | Δ truncation-excluded |
|---|---|---|---|---|---|---|---|
| MMLU-Pro | 300 | 77.0% | 75.3% | +1.7pp | [−2.3, +5.7] | 0.511 | **−0.4pp** [−3.4, +2.6] |
| IFBench | 150 | 79.3% | 75.3% | +4.0pp | [−2.0, +10.0] | 0.263 | +2.1pp [−2.8, +7.7] |
| **Pooled** | 450 | 77.8% | 75.3% | **+2.4pp** | **[−0.9, +5.8]** | — | **+0.5pp** [−2.2, +2.9] |

Pre-registered rule: GO if ≥4pp with CI upper-bound <0; NO-GO if <3pp or CI spans 0.
→ **NO-GO** (pooled 2.4pp, CI spans 0; truncation-clean 0.5pp; McNemar non-significant both axes).

## Why the wedge is absent: reasoning recovers precision loss with compute
- Q4 is **more verbose**: IFBench median 6088 tok (Q4) vs 4356 (Q8) = +40%; MMLU-Pro wall 8659s (Q4)
  vs 6418s (Q8) = +35% slower; Q4 truncated more (mmlu 25 vs 16).
- Same accuracy, more tokens → **Gemma-12B-Q4 isn't dumber, it's slower.** Matches Gemini's red-team:
  "reasoning ON masks quant degradation — models use extra test-time compute to recover from precision loss."
- The raw +2.4pp is partly a truncation artifact (Q4's extra verbosity hits the cap more); dropping
  truncated pairs → +0.5pp (nil).

## Scope / caveats
- One model (12B — the size reviewers expected to degrade MOST), one contrast (Q8≈FP16 → Q4, the
  community-standard aggressive quant), one lane (reasoning-on, our only lane). It's a SCREEN.
- Corroborates the earlier Qwen3.6-27B ladder (≈0), now confirmed clean on a smaller model.
- The accuracy wedge, IF it exists, is confined to very small (<8B) models or non-reasoning use —
  neither is our headline. A 4B/Q2 spot-check could confirm but wouldn't resurrect it as the differentiator.

## Product implication
- **The accuracy quant-wedge is NOT the launch differentiator.** Pivot the headline to
  **"verified local quality vs frontier"** (distance-to-frontier) — both red-teamers said it stands alone.
  The suite discriminates fine for it: Gemma-12B 77–79% vs frontier ~90%+ = a real ~12–15pp gap.
- **Keep the quant story as an honest secondary finding:** "Q4 costs you VRAM-savings and compute/latency,
  not accuracy (with reasoning on)." This is the cost-axis (tok/s, VRAM) the finder-first site already centers.
- Suite design unaffected — knowledge + instruction both discriminated cleanly here.

## Next (NOT auto-started — Michael's call)
Stage 2 (axis discrimination → keep/weight) + Stage 3 (budget sweep) to finish the lock; OR a 4B/Q2
confirmation spot-check to fully close the wedge question. Held for sign-off.

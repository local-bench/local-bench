# SUITE-v1.2 — LOCKED METHODOLOGY (2026-06-18)

*Locked by Claude from: 2 frontier red-teams (gpt55-review.md, gemini-review.md) + Michael's sign-off
(DECISION.md) + wedge-gate data (WEDGE-RESULT.md) + existing discrimination evidence. This ends the
methodology debate. Reversible ONLY if new discrimination data contradicts a specific call.*

## Lane (locked)
Reasoning-ON only ("capped-thinking"). Graceful reasoning-budget 8192 (confirm via budget sweep).
max_tokens ceiling 16384. Serve f16 KV, 64k standard context, >=12k tokens/slot. Composite within lane only.

## Headline axes (the scored composite)
| Axis | Bench | Status | Evidence |
|---|---|---|---|
| Knowledge | MMLU-Pro | KEEP | discriminates — Gemma-12B 77% vs frontier ~90% |
| Instruction | IFBench | KEEP | discriminates — Gemma-12B 79% |
| Long-context | RULER-32k | KEEP (candidate) | differentiator; confirm local discrimination on first ladder |
| Math | mixed-difficulty (REBUILD) | PENDING | amo+olymmath floors locals ~0; not headline until rebuilt to a 10-70% local band |

Headline composite = equal-weight over VALIDATED discriminating axes (Knowledge + Instruction now; add
Long-context + Math once confirmed/rebuilt). Move to spread-proportional weights once >=3 axes validated.
**ONE signed manifest is the sole weight source** — delete the suite.json axis-weight copy + web COMPOSITE_WEIGHTS.

## Demoted to EXPERIMENTAL (shown on model/run pages, NOT in headline composite)
- Coding: LCB output-prediction — saturated ("decorative" per red-team).
- Agentic: BFCL single-turn (AST, gameable/saturated) + BFCL-multi-turn — profile axes; multi-turn may
  promote to headline if it discriminates.

## Quant / degradation reporting (from WEDGE-RESULT.md)
Accuracy wedge ~nil with reasoning on. Report quant tradeoff as VRAM + speed (tok/s); quality is a ~flat
reassurance line; show the low-end cliff if one exists. Per-model quant LADDER drives the model page.

## Stats (locked)
Three estimands kept distinct: run-to-run repeatability CI · paired quant-delta CI · cross-item generalization CI.
Report weakest-axis alongside composite. No equal-weight claim until all headline axes discriminate.

## Retired / NOT doing
- Difficulty-stratification (both red-teams: over-engineering for launch).
- Answer-only lane (Michael: users run reasoning-on).
- Quant-accuracy-wedge as the headline differentiator (wedge-gate NO-GO).

## Open EXECUTION (no more methodology debate)
1. Seeded quant ladders per popular model (quality + VRAM + tok/s) — model pages. [STARTED: Gemma-4-12B]
2. Rebuild math -> mixed-difficulty set (locals 10-70%).
3. Reconcile 3 weight sources -> 1 signed manifest (code; delegate to codex).
4. Frontier anchors on locked suite ($-gated — Michael's OK).
5. Build site on real data (delete demos, fix composite, finder-first per website-design-v2.md).

# LADDER-RESULT — Gemma-4-12B quant matrix (2026-06-19)

*First real model-page quant ladder. Reasoning-on, f16 KV, 12k/slot, suite-v1.2 core (MMLU-Pro 300 +
IFBench 150). Q8/Q4 from the wedge gate (2026-06-18); Q6/Q5/Q3 from the overnight ladder. Server killed,
GPU idle on completion. Raw accuracy shown (chance-corrected available in run JSONs).*

## The matrix
| Quant | VRAM* | MMLU-Pro | IFBench | avg Δ vs Q8 | mean tok (mmlu) | fails M/I** | tok/s (mmlu)*** |
|---|---|---|---|---|---|---|---|
| Q8_0   | 22.3 GB | 77.0% | 79.3% | —     | 7385 | 15/0 | 345 |
| Q6_K   | 20.3 GB | 78.0% | 81.3% | +1.5  | 7365 | 14/0 | 362 |
| Q5_K_M | 18.9 GB | 81.7% | 82.7% | +4.1  | 6922 | 2/0  | 207 |
| Q4_K_M | 17.9 GB | 75.3% | 75.3% | −2.0  | 7833 | 21/0 | 271 |
| Q3_K_M | 16.4 GB | 70.0% | 74.0% | −5.7  | 8648 | 39/0 | 323 |

\*full-process VRAM at serve (weights + 72k f16 KV + desktop). \*\*fails = no-answer/truncation (proxy for
hitting the 12k/slot cap). \*\*\*tok/s UNRELIABLE here — see caveats.

## Read
- **Q8 → Q4 is FLAT** (75–82%, all within ~±5pp n=300 noise; Q5 nominally top is noise, not a real peak).
  No quality cost from Q8 down to Q4, saving ~4.4 GB VRAM (22.3→17.9). Confirms the wedge NO-GO across the curve.
- **Q3 is the CLIFF:** −5.7pp avg (MMLU 70%), and 39 fails — Q3 is both weakest AND most verbose (8648
  mean tok): struggling → rambling → truncating. Don't go below Q4 on this model.
- **Sweet spot = Q4_K_M** (smallest holding quality; 17.9 GB fits a 24 GB card with room). Q3 saves only
  ~1.5 GB more and costs real quality.

## Caveats (honest)
- n=300/150 → ±~5pp per rung; trust the SHAPE (flat Q8–Q4, cliff at Q3), not exact within-cluster ordering.
- Q3's drop is partly truncation (39 fails). A truncation-clean re-check (or 16k/slot) would refine the cliff
  depth, but Q3 is clearly the floor.
- **tok/s is NOT reliable here:** Q5 logged 207 vs Q6 362 — overnight system variance, not the quant (these
  are batched parallel-6 aggregates run across the night). VRAM is clean + monotonic. The model-page SPEED
  column needs a dedicated clean single-stream re-measure; quality + VRAM are solid now.
- One scorer error on Q5_K_M-mmlu (1 item, usage.completion_tokens=None) — negligible.

## Model-page takeaway
"Gemma-4-12B: run Q4–Q6 — quality holds flat, you just trade VRAM. Q3 is the cliff (−6pp, heavy
truncation). Sweet spot Q4_K_M for 24 GB cards." This IS the "which quant should I run?" matrix on real data.

## Next
- Clean single-stream tok/s pass per rung for the speed column.
- More models (Qwen, a distill) for breadth; frontier anchors ($-gated) for the "vs frontier" spine.
- Wire this into the model page (delete demo data, one signed composite).

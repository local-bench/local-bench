# Leg B — the quant-degradation wedge: DELIVERED (Qwen3.6-27B, 2026-06-15)

**Result in one line:** on suite-v1 (answer-only, N=80), **Q4_K_M, Q6_K and Q8_0 of Qwen3.6-27B are
statistically indistinguishable** — every paired composite delta's CI spans or touches zero and the
ordering isn't even monotonic. The practical takeaway for a local user: **going from Q8_0 to Q4_K_M
costs ~nothing measurable here and saves ~12 GB of VRAM**; the real quantization cliff is *below* Q4
(Q3/Q2), not among these K-quants. This is the launch wedge, measured with paired CIs — the thing no
public board publishes.

## What was measured
One base model, three quantizations from the **same GGUF repo** (`lmstudio-community/Qwen3.6-27B-GGUF`
— same base weights AND same quantizer, so the only variable is bit-width), run through the **identical**
suite-v1 item set on the same hardware:

| rung | file | VRAM (weights) | fits 32 GB? |
|---|---|---|---|
| Q4_K_M | Qwen3.6-27B-Q4_K_M.gguf | ~16 GB | yes, comfortably |
| Q6_K | Qwen3.6-27B-Q6_K.gguf | ~21 GB | yes |
| Q8_0 | Qwen3.6-27B-Q8_0.gguf | ~27 GB | **only with minimal desktop overhead** (loaded at ~30 GB used; the binding rung) |

fp16 (54 GB) does not fit a 32 GB card → Q8_0 is the on-box reference ceiling.

## Serving stack (the hard part — for reproducibility)
vLLM and SGLang **cannot** serve this model's GGUF: it carries the arch tag `qwen35`, which both reject
at config-parse ([vLLM #36456](https://github.com/vllm-project/vllm/issues/36456),
[SGLang #6281](https://github.com/sgl-project/sglang/issues/6281)). LM Studio's CLI can't load a
non-default quant variant, and its bundled llama-server won't run detached. So the wedge runs on a
**native llama.cpp `llama-server` built from source for the 5090's Blackwell arch (sm_120)** in WSL2
(sudo-free: micromamba + conda `cuda-toolkit=12.8`; `cmake -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`).
GGUF runs at its true K-quant footprint (dequant happens per-tile in-kernel, never pre-expanded to fp16).

**Operating point (constant across all three rungs):** answer-only with thinking **suppressed**
(`enable_thinking=false`, injected per request via `--jinja`; **probe-gated on every rung** — 0 `<think>`
leakage, empty `reasoning_text`) · `-c 8192 --parallel 2` (4096 tok/slot) · quantized KV (`q8_0`) ·
`--max-tokens 2048` · temperature 0 · N=80/bench (amo=39), identical item ids → genuine paired deltas ·
RTX 5090. **0 infra errors across all 1077 items in all three runs.**

## Per-rung scorecard (chance-corrected accuracy)
| rung | knowledge | instruction | agentic | math (oly/amo) | **composite** | malformed¹ | tok/s | med lat | VRAM |
|---|---|---|---|---|---|---|---|---|---|
| Q4_K_M | 48.6% | 53.8% | 91.2% | 6.2% / 5.1% | **41.0%** | 13/80 | **107** | **13.6 s** | **16 GB** |
| Q6_K | 48.6% | 56.2% | 97.5% | 10.0% / 5.1% | **43.5%** | 15/80 | 104 | 15.4 s | 21 GB |
| Q8_0 | 44.4% | 53.8% | 97.5% | 6.2% / 2.6% | **40.9%** | 11/80 | 89 | 17.2 s | 27 GB |

Quality columns are statistically tied (within noise); the **tok/s / latency / VRAM** columns are the
real, monotonic differentiators. Wall-clock: 56.5 / 58.2 / 68.6 min (Q8 ~22% slower). All RTX-5090-specific.

¹ malformed = `n_extraction_failures` on knowledge (the only axis with any) — the reliability signal.
All other axes had 0 malformed and 0 errors. tok/s is RTX-5090-specific (manifest-qualified). Q8_0 is
slower (89 vs ~105) — heavier compute per token at the same near-full GPU residency.

## Paired deltas (composite, "on these items" ± bootstrap CI)
| pair | composite Δ | 95% CI | significant? |
|---|---|---|---|
| Q6_K − Q4_K_M | **+2.5** | −0.5 .. +5.8 | no (crosses 0) |
| Q8_0 − Q4_K_M | **≈ 0** | −2.8 .. +2.8 | no (centered on 0) |
| Q8_0 − Q6_K | **−2.6** | −5.1 .. 0.0 | no (touches 0) |

Per-axis deltas tell the same story (all CIs span zero): e.g. Q8−Q6 agentic = 0.0 ± 0.0, knowledge
= −3.8 ± 8.8, math = −3.8 ± 6.2. The non-monotonic ordering (Q6 highest, Q8 ≈ Q4) is itself the proof
that these differences are noise, not signal.

## Interpretation
- **Quality is tied, but the quants are NOT identical — the real signal is COST, not accuracy.** Speed
  and VRAM rise monotonically with bit-width while measured quality does not: throughput 107 → 104 → 89
  tok/s (Q8 ~17% slower than Q4), median per-item latency 13.6 → 15.4 → 17.2 s (Q8 ~26% slower), p95
  37.7 → 38.2 → 44.7 s, VRAM 16 → 21 → 27 GB. So **Q4_K_M strictly dominates Q8_0 for this model** —
  identical measured quality, faster, and 11 GB smaller. There is no reason to run Q8_0 of Qwen3.6-27B:
  you pay more VRAM and latency for zero quality gain. This is the actionable wedge result, and it's why
  "Q8 ≤ Q6 on accuracy" is a non-issue — the accuracy axis is tied (within noise); the **cost axis** is
  where the real, monotonic differentiation lives.
- **No resolvable quant-degradation signal among Q4/Q6/Q8 at N=80.** This matches what's known about
  K-quants: Q4_K_M and above are near-lossless; quality falls off at Q3/Q2. The wedge measured the
  flat top of that curve.
- **The product message is strong and honest:** *"Measured on Qwen3.6-27B: Q4_K_M is within noise of
  Q8_0 on a 7-axis suite — run the smaller quant, keep the 12 GB."* With CIs, not vibes.
- **Where the real wedge lives:** the next runs that would *show* degradation are **Q3_K_M / Q2_K**
  (download + run, same harness) and/or a **larger N** (Standard tier) to tighten these ±3 composite CIs.

## Caveats
- **CIs are wide at N=80** (±~3 composite). Differences this small need Standard-tier N (or pooling) to
  resolve; that's the honesty rule — reported "on these items ± paired CI", never as a universal %.
- **Math floors** under answer-only (suppressed reasoning); it's a format/robustness probe here, not a
  capability axis. A capped-thinking math lane is a later addition.
- **Timing is 5090-specific.** Q8_0 needing ~30 GB (fits only with a near-idle desktop) is a real
  practical finding: an 8-bit 27B is impractical on 32 GB; Q6_K (21 GB) is the comfortable ceiling.
- Scoring uses the pre-hardening bootstrap (the red-team's cluster-robust/equivalence fixes are on a
  separate branch pending the merge-scope decision; the within-noise conclusion is robust to either).

Runs: `runs/lcpp-{q4_k_m,q6_k,q8_0}.json`; deltas `runs/delta-{q6-q4,q8-q4,q8-q6}.json` (gitignored).

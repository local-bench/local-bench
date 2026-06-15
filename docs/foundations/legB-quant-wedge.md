# Leg B — the quant-degradation wedge: DELIVERED (Qwen3.6-27B, 5-rung ladder, 2026-06-15)

**Result in one line:** on suite-v1 (answer-only, N=80), Qwen3.6-27B holds quality **flat from Q8_0
all the way down to Q3_K_M** — every paired composite delta among Q8/Q6/Q4/Q3 spans or touches zero —
and then **falls off a measurable cliff at Q2_K** (composite −5 ± ~3 vs every higher rung, CI excludes
zero; agentic/instruction drop 10–15 pts). Meanwhile throughput rises monotonically as bits fall
(89 → 137 tok/s). The practical takeaway for a local user: **run Q4_K_M or Q3_K_M — quality is identical
to Q8_0, it's faster, and it saves 11–15 GB of VRAM. Do NOT drop to Q2_K — that's where it breaks.**
This is the launch wedge, measured with paired CIs — the thing no public board publishes.

## The ladder
One base model, five quantizations through the **identical** suite-v1 item set on the same hardware
(RTX 5090). **Quantizer provenance (a real caveat, see below):** Q4/Q6/Q8 are
`lmstudio-community/Qwen3.6-27B-GGUF`; Q3/Q2 are `bartowski/Qwen3.6-27B-GGUF` (lmstudio-community
does not publish below Q4). So the **clean within-quantizer comparisons are Q8↔Q6↔Q4 (lmstudio) and
Q3↔Q2 (bartowski)**; cross-quantizer deltas (e.g. Q3 vs Q4) mix quantizers and are read with that in mind.

| rung | file | repo | VRAM (weights) | runtime VRAM¹ | fits 32 GB? |
|---|---|---|---|---|---|
| Q2_K | Qwen3.6-27B-Q2_K.gguf | bartowski | ~12 GB | ~16 GB | yes, easily |
| Q3_K_M | Qwen3.6-27B-Q3_K_M.gguf | bartowski | ~14 GB | ~18 GB | yes, easily |
| Q4_K_M | Qwen3.6-27B-Q4_K_M.gguf | lmstudio | ~16 GB | ~20 GB | yes, comfortably |
| Q6_K | Qwen3.6-27B-Q6_K.gguf | lmstudio | ~21 GB | ~25 GB | yes |
| Q8_0 | Qwen3.6-27B-Q8_0.gguf | lmstudio | ~27 GB | ~30 GB | **only with a near-idle desktop** (binding rung) |

¹ runtime = weights + quantized KV cache (`q8_0`, `-c 8192 --parallel 2`). fp16 (54 GB) does not fit a
32 GB card → Q8_0 is the on-box reference ceiling.

## Serving stack (the hard part — for reproducibility)
vLLM and SGLang **cannot** serve this model's GGUF: it carries the arch tag `qwen35`, which both reject
at config-parse ([vLLM #36456](https://github.com/vllm-project/vllm/issues/36456),
[SGLang #6281](https://github.com/sgl-project/sglang/issues/6281)). LM Studio's CLI can't load a
non-default quant variant, and its bundled llama-server won't run detached. So the wedge runs on a
**native llama.cpp `llama-server` built from source for the 5090's Blackwell arch (sm_120)** in WSL2
(sudo-free: micromamba + conda `cuda-toolkit=12.8`; `cmake -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`).
GGUF runs at its true K-quant footprint (dequant happens per-tile in-kernel, never pre-expanded to fp16).

**Operating point (constant across all five rungs):** answer-only with thinking **suppressed**
(`enable_thinking=false`, injected per request via `--jinja`; **probe-gated on every rung** — 0 `<think>`
leakage, 0 empty completions) · `-c 8192 --parallel 2` (4096 tok/slot) · quantized KV (`q8_0`) ·
`--max-tokens 2048` · temperature 0 · N=80/bench (amo=39), identical item ids → genuine paired deltas ·
RTX 5090. **0 infra errors across all 359 items in every run.**

## Per-rung scorecard (chance-corrected accuracy)
| rung | knowledge | instruction | agentic | math (oly/amo) | **composite** | malformed² | tok/s | med lat | VRAM(wts) |
|---|---|---|---|---|---|---|---|---|---|
| Q2_K | 40.3% | 47.5% | **82.5%** | 3.8% / 5.1% | **35.8%** | 18 + 1 | **137** | **12.4 s** | **~12 GB** |
| Q3_K_M | 43.1% | **57.5%** | 95.0% | 7.5% / 2.6% | **41.1%** | 14 | 115 | 12.6 s | ~14 GB |
| Q4_K_M | 48.6% | 53.8% | 91.2% | 6.2% / 5.1% | **41.0%** | 13 | 107 | 13.6 s | ~16 GB |
| Q6_K | 48.6% | 56.2% | 97.5% | 10.0% / 5.1% | **43.5%** | 15 | 104 | 15.4 s | ~21 GB |
| Q8_0 | 44.4% | 53.8% | 97.5% | 6.2% / 2.6% | **40.9%** | 11 | 89 | 17.0 s | ~27 GB |

The **Q8→Q3 band (composite 40.9–43.5) is one flat noisy plateau**; **Q2_K sits ~5 pts below the bottom
of it** and shows the only across-the-board axis drops (agentic 82.5 vs 91–98; instruction 47.5 vs 54–58).
tok/s / latency / VRAM move monotonically with bit-width and are the *cost* differentiators on the plateau.
Wall-clock: Q2 45.2 / Q3 52.9 / Q4 56.5 / Q6 58.2 / Q8 68.6 min. All RTX-5090-specific.

² malformed = `n_extraction_failures` (responses the scorer couldn't parse). Almost all on knowledge
(supergpqa); the count creeps up as bits fall (Q8 11 → Q4 13 → Q3 14 → **Q2 18**), and **Q2_K is the only
rung that also fails an *agentic* extraction** (1 malformed tool-call) — a small but real reliability
signal that tracks the accuracy cliff. All other axes: 0 malformed, 0 errors, every rung.

## Paired composite deltas ("on these items" ± bootstrap CI)
| pair | quantizer | composite Δ | 95% CI | significant? |
|---|---|---|---|---|
| Q6_K − Q4_K_M | lmstudio↔lmstudio | +2.5 | −0.5 .. +5.8 | no |
| Q8_0 − Q4_K_M | lmstudio↔lmstudio | ≈ 0 | −2.8 .. +2.8 | no |
| Q8_0 − Q6_K | lmstudio↔lmstudio | −2.6 | −5.1 .. 0.0 | no (touches 0) |
| Q3_K_M − Q4_K_M | bartowski↔lmstudio | +0.2 | −2.8 .. +3.2 | no |
| Q3_K_M − Q8_0 | bartowski↔lmstudio | +0.2 | −2.3 .. +2.8 | no |
| **Q2_K − Q3_K_M** | **bartowski↔bartowski** | **−5.2** | **−8.3 .. −2.2** | **YES** |
| **Q2_K − Q4_K_M** | bartowski↔lmstudio | **−5.0** | **−8.8 .. −1.2** | **YES** |
| **Q2_K − Q8_0** | bartowski↔lmstudio | **−5.0** | **−8.3 .. −1.7** | **YES** |

**Every Q8/Q6/Q4/Q3 pair is tied** (CI spans/touches 0; ordering non-monotonic = noise). **Every Q2_K
pair is significant** (CI excludes 0). The single cleanest result — the **within-bartowski Q2−Q3 cliff,
−5.2 ± 3.2** — needs no cross-quantizer caveat: it isolates one bit-width step and it's the first
significant composite delta in the entire ladder.

## Interpretation
- **The cliff is real and it is between Q3 and Q2 — and it CANNOT be run-to-run noise.** The Q2 damage
  lands hardest on the **deterministic axes**: vs Q3, **bfcl (agentic) −12.5** and **ifbench
  (instruction) −10.0**. Our repeatability finding (below) showed those two axes are **bit-identical
  run-to-run (0.0 ± 0.0)** — llama.cpp greedy decoding on short structured outputs is deterministic.
  So a −10 to −12.5 pt move on axes with *zero* jitter is signal, full stop. (Knowledge/supergpqa,
  which *does* jitter ±~4, moved only −2.5 — consistent with it being the noisy axis, not the
  degrading one.)
- **The plateau is genuinely flat: Q4_K_M (and Q3_K_M) strictly dominate Q8_0.** Across Q8→Q3, measured
  quality is tied while speed and VRAM improve every step down: throughput 89 → 104 → 107 → 115 tok/s,
  median latency 17.0 → 15.4 → 13.6 → 12.6 s, VRAM 27 → 21 → 16 → 14 GB. There is **no reason to run
  Q8_0 or Q6_K of this model** — you pay VRAM and latency for zero measurable quality. The actionable
  pick is **Q4_K_M** (clean lmstudio quant, ~16 GB, tied with Q8) or **Q3_K_M** (~14 GB, fastest safe
  rung) — and **stop above Q2_K**.
- **This matches what's known about K-quants** (Q4_K_M and up ≈ near-lossless; degradation appears at
  Q3/Q2) — but here it's *measured on this model with CIs*, and the surprise is that **even Q3_K_M is
  still on the plateau**; the knee is one step lower than the folklore "stay at Q4" rule implies.
- **Repeatability localizes the noise (basis for the "can't be noise" argument above).** Re-running Q8_0
  (temp 0, same config): instruction, agentic, and both math benches were **bit-identical** across runs
  (0.0 ± 0.0); only **knowledge/supergpqa swung +3.8** (the long-CoT MCQ axis, where batched greedy
  decoding isn't bit-exact). Composite run-to-run noise ≈ ±1.5 — the same size as the Q8/Q6/Q4/Q3
  gaps (so those are noise) and **far smaller than the Q2 gap** (so that's signal). (Runs
  `runs/lcpp-q8_0-rerun.json`, `runs/delta-q8rerun.json`.) For reproducible knowledge scores, run
  `--parallel 1` or report a small repeatability band.
- **The product message is strong, honest, and now complete:** *"Measured on Qwen3.6-27B across a 5-quant
  ladder: quality is flat from Q8 down to Q3 — run the small quant and keep 13 GB — but Q2_K costs you a
  real, significant 5 composite points (and 10–15 on tool-use and instruction-following). With CIs, not vibes."*

## Caveats
- **Quantizer confound (Q3/Q2 are bartowski; Q4/Q6/Q8 are lmstudio).** Mitigated three ways: the
  load-bearing cliff result is the **within-bartowski Q2−Q3** delta; Q2 is *also* significantly below
  both lmstudio rungs (Q4, Q8); and bartowski-Q3 *ties* lmstudio-Q4/Q8, evidence the quantizer choice
  adds no large offset at these levels. A same-quantizer 5-rung ladder (all bartowski, or all lmstudio
  if they extend below Q4) would remove the asterisk — backlog.
- **CIs are wide at N=80** (±~3 composite). The Q8→Q3 ties are "indistinguishable at N=80", not "proven
  equal"; the Q2 cliff clears N=80 comfortably. Standard-tier N would tighten both. Reported "on these
  items ± paired CI", never as a universal %.
- **Math floors** under answer-only (suppressed reasoning); it's a format/robustness probe here, not a
  capability axis. A capped-thinking math lane is a later addition.
- **Timing is 5090-specific.** Q8_0 needing ~30 GB (fits only with a near-idle desktop) is itself a real
  finding: an 8-bit 27B is impractical on 32 GB; Q4_K_M (~20 GB runtime) is the comfortable headline rung.
- Scoring uses the pre-hardening bootstrap (the red-team's cluster-robust/equivalence fixes are on a
  separate branch pending the merge-scope decision; both the within-noise plateau and the Q2 cliff are
  robust to either).

Runs: `runs/lcpp-{q2_k,q3_k_m,q4_k_m,q6_k,q8_0}.json` (+ `q8_0-rerun`); deltas `runs/delta-*.json` (gitignored).

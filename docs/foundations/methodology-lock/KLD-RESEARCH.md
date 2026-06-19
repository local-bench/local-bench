# Quant-degradation metric research — ADOPT KL-divergence (2026-06-19)

*Deep-research harness (102 agents, 20 sources, 25 claims adversarially verified, 23 confirmed).
Question: how do the GGUF/HF-ecosystem experts (Unsloth, bartowski, llama.cpp) benchmark quant quality,
and should local-bench adopt KL-divergence? Full result: tasks/wndnho365.output.*

## VERDICT: adopt KL-divergence vs the full-precision model as the quant-degradation metric.
It is the expert gold-standard, far more sensitive than task-accuracy, and **it is exactly the signal our
flat-accuracy-then-cliff Gemma result was missing.** A 2026 paper ("A KL Lens on Quantization", arXiv
2604.13440) documents our exact pattern: *"accuracy remains stable while KL divergence remains small, then
degrades as divergence increases."* So accuracy masks a smooth degradation that KLD surfaces.

## Why KLD (not perplexity, not accuracy)
- Unsloth: *"KL Divergence should be one of the gold standards for reporting quantization errors"* (cites
  "Accuracy is Not All You Need", arXiv 2407.09141). And: *"Using perplexity is incorrect since output
  token values can cancel out, so we must use KLD or harder benchmarks."* → sensitivity ordering:
  **KLD > perplexity > task-accuracy.**
- KLD measures how far the quantized model's output **distribution** drifts from FP16 (0 = identical).
  That's the distribution-level signal accuracy can't see when reasoning recovers the right answer anyway.

## How (free, first-party — llama.cpp `llama-perplexity`, two-pass)
1. **Baseline:** run FP16/BF16 model with `--kl-divergence-base model-f16.kld` → records + saves all logits.
2. **Score each quant:** `llama-perplexity -m quant.gguf -f calib.txt --kl-divergence-base model-f16.kld --kl-divergence`.
Emits a rich per-quant panel: KLD (mean + percentiles), mean/RMS change in correct-token probability,
Pearson correlation, **"Same top p"** (how often both models pick the same top token), and a built-in
heuristic: *symmetric percentiles = harmless noise; negative-skewed = the model is genuinely getting worse.*
(llama.cpp also now ships `--target-bpw` optimal-recipe tooling that publishes muPPL/rho-PPL/muKLD/Same-Top-P.)

## Run it ourselves — do NOT import the experts' numbers
Strongly cautioned by the sources: published per-quant numbers are **calibration/imatrix-dependent + vendor
self-benchmarked + often single-model**, and the experts themselves warn *lower KLD/PPL does not guarantee
better real-world task performance* (Unsloth shows a case where a worse-KLD quant wins real evals). The
methodology is trustworthy; the headline numbers are not plug-and-play. So: **adopt the method, run KLD
ourselves with disclosed/controlled calibration, and pair KLD with our task evals** (neither alone is a verdict).

## Implementation notes / open questions (from the research)
- The FP16 baseline (the heavy pass) is computed **once per model** and reused across its quants. A llama.cpp
  maintainer publishes WikiText-2 FP16 logits, but they're model-specific — we generate our own per target model.
- **Calibration set** matters: avoid the calibration-overfitting trap (don't eval wikitext on a
  wikitext-calibrated quant). Open: wiki.test.raw (the convention) vs a held-out/diverse set.
- **KLD aggregate** to headline: mean KLD vs 99.9th-percentile vs median+q99 — experts disagree; the choice
  matters most for reasoning models (outlier-driven). Open.
- KLD is **sensitivity-faithful, not a quality oracle** — high-sensitivity ranking/early-warning, paired with task evals.

## Strategic implication: this REVIVES the quant wedge
Our gate found accuracy ~flat → the wedge *looked* dead. But accuracy was the wrong, under-sensitive lens.
KLD is the right one. So we can have a **rigorous, differentiated quant-cost story after all**: "Q4 shifts
Gemma-12B's output distribution from FP16 by X KLD" — the experts' gold-standard metric, measured on our own
runs, paired with task evals. The model page becomes: **KLD degradation curve (the smooth signal) + VRAM +
speed**, with task-accuracy as the coarse "does it still get the answer" check. The differentiator is back,
measured correctly.

## Recommended next experiment (sign-off gated — benchmarks on hold)
Run llama.cpp KLD on the **exact Gemma-12B Q8→Q3 ladder** (need a BF16/FP16 baseline ~24GB on the 5090, or
use Q8_0 as a near-lossless reference proxy). Prediction: KLD rises smoothly across Q8→Q4 and jumps at the
Q3 cliff — confirming KLD gives the early-warning signal accuracy missed, and (separately) testing whether
reasoning-token recovery also blunts KLD. This is the validating run before we commit the metric to the suite.

## FLAG (unrelated, surfaced as a source — worth checking)
The research cited **localbench.substack.com** with posts "gguf-benchmark-methodology",
"qwen-3-6-27b-gguf-quality-benchmark", "kv-cache-quantization-benchmark" — eerily close to our exact project
and experiments. Either a name-collision/competitor in our precise niche, our own (?), or a research
artifact. Worth verifying — the name overlap + topic overlap is notable.

## Key sources
- llama.cpp perplexity README (KLD def + two-pass + heuristic): github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md
- Unsloth Dynamic-2.0 GGUFs (KLD as gold standard): unsloth.ai/docs/basics/unsloth-dynamic-2.0-ggufs
- "Accuracy is Not All You Need" arXiv 2407.09141 · "A KL Lens on Quantization" arXiv 2604.13440
- Shared FP16 logits (maintainer): huggingface.co/JohannesGaessler/llama.cpp_wikitext_logits
- `--target-bpw` / per-quant KLD tables: github.com/ggml-org/llama.cpp/discussions/15576

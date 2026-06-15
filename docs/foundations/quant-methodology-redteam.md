# Quant-degradation methodology — 3-frontier-model red-team (2026-06-14)

Adversarial review of local-bench's **core wedge** — the within-model quant-degradation measurement
(paired frozen-item delta in `scoring/paired_delta.py`) + the `suite-v1-DECISION.md` §3 **Leg B**
validation probe. Three independent frontier models, different lineages, each told to attack across
nine axes and output a structured verdict. Raw verdicts: `redteam/{gpt55,gemini,qwen}-quant-review.json`.

## Verdicts
| Reviewer | Verdict | Biggest risk (one line) |
|---|---|---|
| **GPT-5.5** (xhigh, codex) | **REVISE** | Will publish confident-looking quant deltas that are mostly power-limited, runtime-confounded, and non-transferable while users read them as causal Q4 cost estimates. |
| **Gemini 3.1 Pro** | **FATAL** | Quick-tier N is mathematically incapable of resolving the 1-3pt deltas the product claims to measure → a leaderboard of false negatives sold as "quant is free." |
| **Qwen 3.7 Max** | **REVISE** | The N=3 FP16 noise floor applied to Q4 guarantees false-positive "severe regressions" driven by kernel non-determinism, not quant damage. |

**Net:** the paired-delta *architecture* is endorsed by all three; the *validation + reporting as
originally specced* (single model, N=3 FP16-only floor, Quick-tier, ≥1-axis gate) was judged unable to
support the wedge's claim. Salvageable, not as written. Gemini's FATAL is specifically about Quick-tier
power — addressed by the Standard-tier+/MDE rewrite below.

## The nine consensus findings (all three independently flagged each)

1. **Statistical power is the dominant problem.** All three ran the McNemar math and converged: a
   typical **1-3pt** quant gap needs **~400 to >1000+ items/axis** at 80% power (GPT-5.5: ~2.1-8.5k for
   3pt, ~19-77k for 1pt; Gemini: ~400-500 for 2pt; Qwen: ~800 discordant pairs / N>1000 for 2pt).
   **Quick-tier (~100-200) cannot resolve quant.** "Q8 is free" at low N = absence-of-evidence.
   → quant claims are **Standard-tier+**, with a pre-registered **MDE per tier** + **equivalence margin**;
   "free" only if the CI sits *inside* the negligible band.
2. **Repeatability floor: N=3 on FP16 is invalid (emphatic, all three).** 3 runs = 2 d.o.f. = no CI;
   and Q4's run-to-run variance differs from (usually exceeds) FP16's. → **per-config floor, N≥10**,
   stratified by runtime.
3. **Multiple comparisons → the severe-regression flag cries wolf.** ~15-60 (axis×stratum×quant) cells,
   no correction → **family-wise false-positive 54-95%**. The −10pt threshold is arbitrary.
   → **FDR (Benjamini-Hochberg) / Holm**, threshold tied to a pre-registered harm margin.
4. **Chance-correcting a discrete {−1,0,+1} delta is mathematically incoherent.** Chance correction
   applies to aggregate success *proportions*, not single-trial signed outcomes; it distorts variance
   and makes MCQ vs generative non-comparable. → apply at the **aggregate config-score** level (or go
   continuous). *(Hits implemented `_delta_item`.)*
5. **Bootstrap independence: stratified-by-difficulty ≠ clustered.** Long-context / multi-turn / RAG
   items share context → correlated → item-level resampling shrinks the CI ~**√(cluster size)** → false
   "real" deltas + false severe-regressions. The handoff *claims* "clustered bootstrap"; the code
   clusters by difficulty stratum. → **cluster-robust by shared-context/prompt-family.**
6. **The degradation-profile hypothesis is FALSE/unproven.** k-quants (Q4_K_M) use importance matrices
   to preserve salient weights → damage is **diffuse**, or shows as **format/parse breakage on EASY
   items** (JSON brackets, stop tokens, high-freq structural tokens), not "hard items / long-context
   first." MCQ isn't automatically robust (logit flips near option boundaries). → treat the profile as a
   **measured result**, and **split format-failures from capability-failures** in scoring so scorer
   brittleness isn't read as reasoning loss.
7. **Quant×runtime confound — "delivered tuple" is a causal dodge for the product claim.** FP16-vLLM vs
   Q4-llama.cpp delta is dominated by kernel/KV-cache/tokenizer, not weights. The product says "what Q4
   costs YOUR model" (causal). → **same-runtime ladders** (vary only quant); cross-runtime/cross-rig =
   labelled **tuple-level, not quant-causal.**
8. **Leg-B generalisation — one model/size validates almost nothing.** Q4 ~catastrophic at 1.5B, ~free
   at 32B; threshold-item distribution is model-specific. → **matrix: ≥3 sizes × ≥2 runtimes**, with a
   **Q3 known-large positive control.**
9. **Gate adequacy — "≥1 axis" is far too weak.** Resolving quant on 1 of 7 axes is useless for ~85-90%
   of users. → PASS = **composite CI excludes zero AND ≥50% of axes resolve at Standard-tier** + the Q3
   positive control fires.

## Notable missed-flaws (beyond the nine attack axes)
- **Binary correctness discards severity** — a near-correct and a nonsense answer both score 0; a
  **paired log-prob/perplexity delta** is ~10× more N-efficient for quant (but needs endpoint logprobs;
  measures distributional shift, not task success → complement, not replacement). *(GPT-5.5, Qwen)*
- **temp=0 MAXIMISES quant sensitivity** (forces the argmax path; a tiny logit flip reroutes the whole
  greedy generation) and doesn't reflect temp>0 real use — determinism vs representativeness tension. *(Qwen)*
- **Pinned max-tokens can manufacture deltas** if one config is more verbose → more truncation. *(GPT-5.5)*
- **Hardware FP non-determinism** (3090 vs M2 Metal) dominates cross-rig deltas. *(Gemini)*
- **Item freezing ↑ contamination/overfit** once the public leaderboard exposes repeated feedback. *(GPT-5.5)*
- **Distill logit-smoothness** changes quant sensitivity → confounds the "distill = just another model"
  framing. *(Qwen)*
- **Percentile bootstrap is poorly calibrated for sparse discordant counts** → prefer exact-McNemar /
  Wilson-style intervals. *(GPT-5.5)*
- **No practical-equivalence margin is defined** → "free" has no statistical meaning. *(GPT-5.5)*

## Disposition (applied to `suite-v1-DECISION.md`)
- **§3 Leg B rewritten** to: multi-model × multi-runtime matrix; Standard-tier+ with pre-registered MDE
  + equivalence margin (Quick-tier exploratory-only for quant); per-config N≥10 floor; same-runtime
  ladders for causal claims; format/capability split; raised gate (composite excludes zero AND ≥50%
  axes + Q3 positive control).
- **§4** gains four **quant-measurement fixes**: drop chance-correction on the discrete delta;
  cluster-robust bootstrap; FDR + per-config floor + exact-McNemar/Wilson for the severe-regression flag;
  evaluate a log-prob/perplexity delta as a higher-power complement.
- **Three of these are code-level** (chance-correction, clustered bootstrap, FDR/interval on
  `subgroups.py`) → implementation + tests required (codex GPT-5.5), not done by this doc edit.

## Harness
Payload `lb-redteam/quant-payload.md`; fired in parallel — GPT-5.5 via `codex exec --sandbox read-only
--skip-git-repo-check`, Gemini 3.1 Pro via REST `generateContent`, Qwen 3.7 Max via OpenRouter
`qwen/qwen3.7-max`; keys read in-process (never echoed); parsed with `quant-parse.js` (ANSI-strip +
last-`"reviewer"` anchor).

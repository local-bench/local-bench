# Quant ladder on suite-v1.1 (reasoning lane) — FINDINGS, 2026-06-17

*First quant-degradation ladder on the rebuilt suite-v1.1 in the `capped-thinking` lane. This is the
Leg-B (within-model resolution) probe from the pre-registered discrimination probe
(`probe-preregistration-v1.1-2026-06-16.md`), run at a SAMPLE size (n=40/axis) ahead of any full-item-set
commitment. Headline: the n=40 sample does **not** resolve a clean wedge, and the reason is itself the finding.*

## What ran
- **Model**: Qwen3.6-27B, native llama.cpp on the 5090 (sm_120), `--parallel 2`, temp 0.
- **Lane**: `capped-thinking` (reasoning ON, calibrated per-axis caps). **Suite**: v1.1.
- **Rungs**: Q6_K (reference, near-lossless) · Q4_K_M · Q3_K_M · Q2_K. Q8 memory-skipped (won't fit -ngl 99);
  Q6 is the lossless stand-in. **ctx** 32768 for Q4/Q3/Q2, 22000 for Q6 (memory) — all items fit either.
- **Axes (5)**: mmlu_pro, ifbench, bfcl, bfcl_multi_turn, lcb. **n=40/axis** (200 items/rung).
  Hard-math excluded (floors at ~0 for locals → no wedge signal, large time cost). RULER excluded (separate
  large-ctx serving pass).
- **Cost**: GPU-time only, **$0**. Wall ~1.5–2h/rung.

## Operational note: a transient CUDA crash (characterised, not quant-related)
The first Q2_K rung died 37 min in — `CUDA error: unknown error` in `ggml_backend_cuda_buffer_set_tensor`
during decode, after ~3.5h of continuous load — voiding bfcl/multi-turn/lcb (mmlu_pro had already finished
clean). A **clean re-run under identical conditions (parallel 2) completed with 0 errors**, so this was a
one-off runtime fault (cumulative-load / driver glitch), **not** a Q2-specific or quant-quality issue. The
re-run script now carries a health-recheck + auto-retry-at-parallel-1 guard. **Lesson for the full run: a
multi-hour ladder needs mid-rung crash resilience — one CUDA blip must not void a rung.**

## The trap: marginal accuracy MISLEADS at this sample size
Per-axis marginal accuracy across rungs (valid items):

| axis | Q6_K | Q4_K_M | Q3_K_M | Q2_K |
|---|---|---|---|---|
| mmlu_pro | 60.0 | 65.0 | 70.0 | 72.5 |
| ifbench | 90.0 | 92.5 | 90.0 | 92.5 |
| bfcl | 100.0 | 80.0 | 95.0 | 97.5 |
| bfcl_multi_turn | 25.0 | 20.0 | 17.5 | 20.0 |
| lcb | 97.5 | 100.0 | 100.0 | 95.0 |

Read naively this is nonsense — `mmlu_pro` is **inverted** (the *worst* quant scores *highest*), `bfcl` is
non-monotonic. At n=40 the marginal CI is ≈±15pts, far wider than any real 2–5pt quant delta. **Publishing
the marginals as a wedge would be the exact "9B ≈ frontier" noise-as-signal failure suite-v1.1 was built to
kill.**

## The correct lens: PAIRED deltas vs the Q6 reference (same items)
`deg` = item Q6 got right that the lower quant got wrong (real degradation); `gain` = the reverse (noise/
Q6-unlucky). One-sided sign test on discordant pairs.

| axis | step | deg | gain | net | p | read |
|---|---|---|---|---|---|---|
| **mmlu_pro** | Q6→Q4 | 1 | 3 | +2 | .312 | only **1** knowledge item ever degrades… |
| | Q6→Q3 | 1 | 5 | +4 | .109 | …deg stays at 1… |
| | Q6→Q2 | 1 | 6 | +5 | .062 | …even to Q2. **Knowledge is quant-robust.** The "inversion" is Q6 sampling-unlucky on ~6 items, not lower quants being better. |
| ifbench | all | 2–3 | 2–4 | ~0 | ≈.5 | symmetric flips = pure noise |
| **bfcl** | Q6→Q4 | **8** | 0 | −8 | **.004** | the one "significant" result — but **non-monotonic** (Q4 worse than Q3/Q2, which is backwards) and at the edge of multiple-comparison significance (15 tests; p_fwe≈.06). Likely a Q4_K_M-mix quirk on a small item cluster — **suggestive, not bankable.** |
| | Q6→Q3 | 2 | 0 | −2 | .250 | |
| | Q6→Q2 | 1 | 0 | −1 | .500 | |
| bfcl_multi_turn | Q4/Q3/Q2 | 4/3/5 | 2/0/3 | −2/−3/−2 | >.1 | all directionally degrading, none significant (low base: Q6 only 10/40) |
| lcb | Q4/Q3 | 0 | 1 | +1 | .5 | **saturated** 95–100% every rung |
| | Q6→Q2 | 2 | 1 | −1 | .5 | first faint coding wobble at Q2 (n=2) |

## Findings (defensible)
1. **Knowledge recall is quant-robust down to Q2** — `deg`=1 on mmlu_pro across *every* rung. Consistent,
   believable, matches the literature (recall survives quantization; precision/reasoning tasks degrade first).
2. **lcb is saturated** (95–100% all rungs) → the pre-registered **down-weight/replace** call is now evidenced,
   not assumed. (Output-prediction at n=40 on a 27B has no headroom.)
3. **Tool-calling is where degradation hints concentrate** — bfcl + bfcl_multi_turn carry every directional
   (negative) paired delta; knowledge/instruction/coding do not. Consistent with tool-use being precision-
   sensitive. But **underpowered at n=40** and the one significant point is non-monotonic.
4. **No robust, monotonic wedge exists at n=40/axis.** Adjacent-quant deltas are smaller than the sampling
   noise. This is the methodological result: **n=40 cannot resolve a 2–5pt quant step** — exactly why the
   probe was pre-registered to use the full fixed sets.

## The strategic reframe (needs Michael)
The **prior** wedge (task #42, OLD saturated suite, **answer-only** lane) reported "flat Q8→Q3, **cliff at
Q2**." This run **does not reproduce a Q2 cliff** — Q2_K holds 72.5/92.5/97.5/95% on knowledge/instruction/
tool/coding. The likely cause is the lane change: **reasoning is error-correcting, so the `capped-thinking`
lane COMPRESSES the quant wedge** — a quantized model that reasons recovers accuracy an answer-only quantized
model loses. (Hypothesis; confirmable only by an answer-only ladder on the *same* suite.)

This flips the launch narrative from "look how much quant damages you" toward a possibly stronger, measured,
counterintuitive story: **"with reasoning on, this 27B is remarkably quant-robust down to Q2 — tool-calling is
the lone soft spot."** Both are publishable; which one we lead with is Michael's call, and it bears on whether
the headline wedge is worth a full-item-set run.

## Recommendation / decision point
The n=40 ladder did its job as a **probe**: harness validated clean across 4 quants, lcb saturation confirmed,
the transient-crash failure mode characterised + guarded, tool-use localised as the degradation candidate, and
the reasoning-lane-compresses-the-wedge reframe surfaced. It is **not** the publishable wedge.

Two paths, both **$0 (GPU-only)** — Michael to choose:
- **A — Full-item-set ladder** (full fixed sets/axis, crash-resilient harness, Q2 included; ~20–30h GPU
  overnight). Gives the paired wedge real power (paired MDE ~1.9pts on the full sets) → either confirms
  quant-robustness or surfaces a sub-noise wedge. Big GPU spend for a possibly-flat result.
- **B — Answer-only confirmation pass first** (cheap, same n=40 items, answer-only lane) to test the
  "reasoning masks degradation" hypothesis *before* committing path A. If confirmed, the lane choice itself
  becomes a headline finding and reframes what the wedge even measures.

My lean: **B then A** — settle what the wedge measures (lane effect) before spending 20–30h GPU measuring it
at full power.

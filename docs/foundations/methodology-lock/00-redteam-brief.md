# Local-Bench suite-v1.1 — independent methodology red-team

You are an independent red-teamer pressure-testing the methodology for a community benchmark
product *before we lock it*. Be adversarial, specific, and decision-forcing. We have burned a
week discovering validity problems by running into them on the GPU; your job is to catch what
we can't see — on paper, before any more compute. Assume we will act on your recommendations.

## The product
"Geekbench for local AI intelligence." Local-LLM users run a frozen quality suite against their
own rig (model x quantization x runtime x hardware) via a CLI; results are server-scored and
placed on a public leaderboard alongside frontier "anchor" models measured on the identical
suite. Verified market gap: LocalScore = speed only; Artificial Analysis = API models only;
HF Open LLM Leaderboard = dead. Nobody publishes community-run *quality* benchmarks on your
actual local setup, anchored to frontier.

Intended differentiator ("the wedge"): the GGUF quant-degradation dataset nobody publishes —
"what does Q4_K_M actually cost model X vs Q6/FP16, measured, with confidence intervals" — plus
distance-to-frontier across the whole local range.

## The suite (adopt-only, v1.1) — 6 axes, equal-weighted (normalized at runtime)
1. Knowledge — MMLU-Pro (400-item fixed stratified subset)
2. Instruction-following — IFBench (programmatic constraint checkers)
3. Math — AMO (39) + OlymMATH-hard (100), pooled
4. Coding — LiveCodeBench, OUTPUT-PREDICTION variant (execution-free, chosen for client-machine safety)
5. Long-context — RULER-32k (60 items)
6. Agentic — BFCL (300, AST-checked) + BFCL-multi-turn (100)

All items run once through a frozen harness; scores comparable only within a suite version.
ToolHop is parked (infra exists, not in v1.1).

## The lane (decided by owner)
Single headline lane = reasoning ON ("capped-thinking"), because real users run their best
settings. Answer-only lane dropped. Graceful server-side reasoning budget = 8192 tokens (the
model concludes its thinking and answers; it is NOT truncated); max_tokens safety ceiling =
16384. Composite computed within the lane only.

## The rig standard (decided by owner)
One RTX 5090 (32 GB). Standard context = 64k, KV cache f16 (NOT quantized — owner's call, doesn't
trust KV-quant). Policy: "run what fits the 5090 at this standard; bounty-board the rest" — users
with bigger rigs contribute the runs we can't.

## What we've measured (the uncomfortable parts — all honest)

A) DISCRIMINATION FAILURE (predecessor suite-v0): on the composite a 9B sat within 6 pts of
   frontier SOTA; 2 of 3 axes were saturated. In v1.1, early signals: coding (LCB output-pred)
   and agentic (BFCL-AST) look SATURATED (frontier and mid-size locals cluster near the top);
   math is FLOORED for locals (~0; only frontier scores meaningfully — published frontier
   ceiling ~0.58). So 3 of 6 axes may not discriminate across the local->frontier range.

B) TRUNCATION BUG (found and fixed this week): the lane used a hard max_tokens cap that
   truncated verbose reasoning mid-thought -> unparseable -> scored WRONG. ~70-100% of
   "knowledge errors" across models were truncation casualties, not real mistakes. MMLU-Pro on
   Qwen3.6-27B: ~60% (truncating) -> 84.4% (graceful budget 4096) -> 93.8% (budget 8192).
   Implication: ALL prior absolute numbers are truncation-depressed and must be re-measured at
   the graceful budget. This is exactly the class of basic validity bug we need you to hunt for.

C) THE WEDGE MIGHT NOT EXIST. The headline differentiator is the quant wedge. Measured on
   Qwen3.6-27B, reasoning ON, ladder Q6->Q4->Q3->Q2 (~200 items/step): the wedge read ~0 and
   NON-MONOTONIC (Q6->Q4 +3.0%, p=0.33; Q6->Q2 -2%, p=0.85). Caveats: (i) confounded by the
   truncation bug (both quants truncated similarly so the paired delta partly cancels), NOT
   cleanly re-measured since the fix; (ii) at n=40/step the design only detects deltas >=17.5%;
   (iii) hypothesis: the wedge is MODEL-SIZE-DEPENDENT — a 27B may be quant-robust while a
   7-12B degrades materially. We have NOT confirmed the wedge exists at any size with clean
   post-fix data.

## Known internal mess (for the composite question)
- Composite weights live in THREE places in code: a hardcoded DOMAIN_WEIGHTS constant (the real
  runtime weights), a decorative copy in suite.json, and a third copy in the web build. Nominal
  axis weights are equal but sum to 1.5 (normalized at runtime). Needs one source of truth.
- A difficulty-stratified-tier redesign (bin items easy/med/hard against a reference-model
  ladder, score band-matched) was designed but NOT built. Open question: right fix for
  saturation, or over-engineering for a solo builder?

## The decisions we need your red-team to FORCE (answer each directly)
1. THE WEDGE: Is a quant-degradation wedge a sound product foundation? Design the MINIMAL clean
   experiment to confirm-or-kill it post-truncation-fix: exact models/sizes (we have a 5090; can
   rent cloud GPUs), which quants, item counts for an adequate MDE (state your target detectable
   delta), and the statistical test. If the wedge is thin at ALL sizes, does the product still
   stand on distance-to-frontier alone? Give an explicit go/no-go decision rule.
2. SATURATION/FLOORING: Given coding+agentic saturate and math floors, what is the right KEEP /
   REWEIGHT / DROP per axis to maximize discrimination across local->frontier? Is
   difficulty-stratification worth the complexity, or is a simpler fix better (harder item
   subsets, drop saturated axes, spread-proportional weighting)?
3. SCOPE: Is a 6-axis suite right for launch, or over-engineered for a solo nights-and-weekends
   builder? If you had to ship in 2 weeks, what is the minimal defensible suite?
4. LANE: Is reasoning-ON-only the right single lane? What do we lose without an answer-only
   "fast mode" comparison, and is that loss acceptable?
5. VALIDITY TRAPS WE'RE STILL MISSING: contamination; scorer brittleness on small/local models
   (do AST/programmatic checkers false-floor weak models and masquerade as "saturation"?);
   graceful-budget under-measuring the most verbose models; KV f16 vs realistic-user-config;
   anything else. List the top ones, ranked, each with a concrete test.
6. COMPOSITE: equal-weight vs spread-proportional vs editorial; single composite vs per-axis
   profile vs worst-axis reporting; how to express the three distinct estimands honestly
   (run-to-run repeatability CI vs paired quant-delta vs cross-item generalization).

## Output contract
- VERDICT (one line): sound-to-lock / sound-with-fixes / needs-rethink.
- For EACH of the 6 decisions: a specific recommendation + reasoning + what evidence would
  change your mind.
- TOP 5 RISKS we're not seeing, ranked, each with a concrete test.
- THE WEDGE: explicit go/no-go + the minimal experiment design (models, quants, n, test, MDE).
- What you would CUT to ship faster.

Be concrete — numbers, item counts, thresholds. Where you are uncertain, say so and state what
would resolve it. Do not hedge into a survey; make calls.

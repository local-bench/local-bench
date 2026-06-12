# External cross-reference audit (2026-06-12)

Purpose: find credible external numbers to (a) sanity-check our anchor runs and (b) cite as
context on model pages — and, by its gaps, confirm why we must run our own anchors. Scope:
current frontier + current popular local models only (per Michael's "latest models" steer).

## Headline conclusion

**Clean, current, citable scores on our exact benches (MMLU-Pro, IFEval) for the latest
frontier models barely exist** — which is the entire justification for running our own
anchors. What exists is scattered, mixed-harness, and often stale:
- Official **TIGER-Lab MMLU-Pro** leaderboard: last updated **2025-02** — predates GPT-5.5 /
  Claude Opus 4.8 / Gemini 3.1 entirely.
- Official **LiveCodeBench** board: last commit **2025-08**; date-windowed by design anyway.
- **IFEval**: never a frontier model-card metric; current numbers (e.g. benchlm.ai) are
  "provisional", unstated provenance.
- Scattered open-model figures (DeepSeek V4 ~92.8% MMLU-Pro; Llama 4 Maverick 85.5 but that
  is *standard* MMLU not Pro; Qwen 3.6-35B quotes GPQA/AIME, not MMLU-Pro) — inconsistent
  harnesses, not comparable to each other or to our runs.

→ Confirms the plan: published numbers are **model-page context only**, never a comparison
spine. Our suite is the only way to get all models on one ruler.

## Strong validation of our scoring methodology (v2)

**Epoch AI's Capabilities Index (ECI)** — 37 benchmarks, the most credible composite in the
field — uses *exactly* the two techniques our v2 spec independently chose:
- **Chance-correction to zero**: "for benchmarks where random guessing would score above 0,
  they rescale so that random guessing is scaled to zero." (= our §2.)
- **IRT** for difficulty/discrimination weighting: each benchmark gets location (difficulty)
  + slope (discrimination) parameters; harder benchmarks contribute more. (= our §7 roadmap.)

Takeaways: (1) our methodology direction is externally vindicated by the gold standard;
(2) ECI is a concrete reference for our 1PL→2PL IRT roadmap; (3) we differ deliberately on
*absolute vs relative* anchoring (ECI rescales across a population for cross-era comparison;
we stay absolute for per-setup temporal stability) — a defensible, documented divergence,
not an oversight. Boggs.tech is a personal ~40-board aggregator built on ECI's method; same
lineage.

## Bench-saturation note (suite-design implication)

MMLU-Pro now sits 90%+ across frontier models ("no longer useful for differentiation" at the
top). Expected and acceptable: anchors will cluster near-ceiling on MMLU-Pro while our
discrimination lives in the local-model region (by design — we measure distance-to-frontier,
not frontier-vs-frontier). But it reinforces methodology v2 §3: watch per-bench discrimination
and treat saturation as a bench-quality signal at the quarterly window. Frontier models also
now ship extended thinking by default → confirms native-reasoning as the correct headline lane.

## What to cite on model pages (context, not baseline)

Per model, link the most credible available source for headline numbers, labeled "reported,
mixed methodology": Epoch ECI / Benchmarking Hub (current, IRT-based, but different benches —
GPQA/HLE/SWE-bench/FrontierMath), Artificial Analysis Intelligence Index, official model
cards. Always alongside — never merged with — our measured suite numbers.

## Sources
- Epoch ECI methodology: https://epoch.ai/benchmarks/eci , https://epoch.ai/data/eci-documentation
- TIGER-Lab MMLU-Pro board (stale 2025-02): https://huggingface.co/spaces/TIGER-Lab/MMLU-Pro
- LiveCodeBench board (stale 2025-08): https://livecodebench.github.io/leaderboard.html
- Boggs dashboard: https://boggs.tech/posts/benchmarks/
- Artificial Analysis: https://artificialanalysis.ai/

# Suite-v1 discrimination probe — v1 verdict (public-data basis, zero-spend, 2026-06-15)

**Question:** for each suite-v1 axis, does it *discriminate* across the model capability range
(weak local → frontier)? Axes that separate models are worth keeping/weighting; saturated or
all-floored axes are not. This sets the (currently `null`) axis weights in `suite/v1/suite.json`.

**Method (and why it's zero-spend):** the discrimination question is about *spread across models*,
which the **official public leaderboards already answer** — they span weak→frontier on every axis,
in the native-reasoning lane. We do **not** need to pay to re-measure current frontier models just to
see whether an axis spreads. (We verified the exact current-frontier-on-our-subset numbers mostly are
*not* published — see the per-axis notes — but the *spread* is, and that's all the keep/weight decision
needs.) Cross-checked against our own measured Qwen3.6-27B runs (answer-only lane, our stratified subset).

**Honesty caveats (this is a provisional v1, not a frozen calibration):**
- Published numbers are a *different harness + the full benchmark set*, not our stratified subset — so
  they ground the **keep/drop + rough weight** decision, **not** exact anchor lines on the measured chart.
- Our local Qwen numbers below are **answer-only** (reasoning suppressed), which floors the reasoning-heavy
  axes (math especially) — a lane artifact, not a capability floor. Local think-on was tested and is
  impractical at scale (≈19 min / 4 items; hard items hit the token cap mid-reasoning or error empty), so
  the published leaderboards (which already include local-tier reasoning models — QwQ, R1-distill, Qwen3-235B)
  are the better source for the local end too.
- Weights are **provisional equal (0.25 each)**. Spread-proportional reweighting awaits a same-harness pass.

## Per-axis discrimination (public spread + our local point)

| axis | bench(es) | published spread (native-reasoning lane, full set) | our Qwen3.6-27B Q4 (answer-only, subset) | discriminates? | verdict |
|---|---|---|---|---|---|
| knowledge | SuperGPQA | R1 61.8 · o1 60.2 · o3-mini-high 55.2 · Claude-3.5 48.2 · Gemini-2.0-flash 47.7 → ~14 pt spread among strong models, more vs weak | 48.6% (cc) | yes | **keep** |
| instruction | IFBench | Grok-4.3 83.3 · Gemini-3.1 ~77 · GPT-5.5 ~76 · Claude ~54–59 → ~28 pt spread (separates even frontier) | 53.8% (cc) | yes | **keep** |
| agentic | BFCL | frontier clusters high (~75+); open-weight Qwen3.7-Max 75 · Nova-2-Pro 61.6 → spreads at mid/low, may saturate at very top | 91.2% (cc) | yes (and our quant ladder moved it 95→82.5 Q3→Q2) | **keep** (saturation-risk; harder agentic set e.g. ToolHop/multi-turn later) |
| math | OlymMATH-HARD + AMO | OlymMATH: Gemini-2.5 58.4 · Qwen3-235B 36.5 · o3-mini 31.2 · QwQ 23.1 · R1 19.5. AMO: Qwen3-Max 65 · Gemini-3 63 · GPT-5 52 → **largest spread (~40 pt)** | 6.2% / 5.1% (cc, answer-only — floored by lane, NOT capability) | yes (strongest) | **keep** |

Sources: SuperGPQA [arXiv 2502.14739](https://arxiv.org/abs/2502.14739); BFCL [gorilla.cs.berkeley.edu](https://gorilla.cs.berkeley.edu/leaderboard.html);
IFBench [arXiv 2507.02833](https://arxiv.org/abs/2507.02833) + Artificial Analysis (current frontier; top-3 directly confirmed,
mid-rows AA-reported); OlymMATH [arXiv 2503.21380](https://arxiv.org/abs/2503.21380); AMO-Bench [arXiv 2510.26768](https://arxiv.org/abs/2510.26768).

## Verdict
- **Keep all four axes.** Every axis shows a clear weak→strong spread in the published reasoning-lane data;
  none floors capable local-tier models (math locals sit 19–37%, not ~0). No axis is dropped at v1.
- **Provisional weights: knowledge 0.25 / instruction 0.25 / agentic 0.25 / math 0.25.** Editorial equal-weight
  per AXIS for v1 (cross-axis spreads aren't on a common measured scale yet). Versioned; revisit with a same-harness pass.
- **Wiring: DONE (#51).** `_scoring.py::composite` and `paired_delta` now both group benches into the 4 axes via
  `BENCH_DOMAINS` (Math = olymmath_hard + amo pooled at one axis-share), weighted equally per axis (`DOMAIN_WEIGHTS`,
  normalized over axes present so suite-v0's 3 axes stay 1/3 each). `suite.json` axis weights set to 0.25. The CLI
  composite now equals the web pipeline's exactly (Qwen3.6-27B Q4 0.499, Q6 0.527, Q8 0.502, Q3 0.504, Q2 0.436);
  the legB wedge doc is re-stated to these per-axis numbers (conclusion unchanged, cliff slightly sharper). 468 tests green.
- **Agentic is the watch-item.** Frontier may saturate BFCL at the top; our quant ladder still shows it
  discriminating (Q2_K −12.5 vs Q3 on bfcl), so it earns its keep at the *local* range we serve. If frontier
  anchors later cluster within 3 pts on BFCL, swap in a harder agentic set (ToolHop / multi-turn).

## Spend decision (answers "can we avoid paying for anchors?")
- **Discrimination probe: NO spend.** Done from public data above.
- **Leaderboard anchor lines (current frontier on OUR subset+harness):** a *separate, launch-time* decision.
  Two honest options: (a) launch citing the public numbers as "reported context" (free, but a different
  harness — never charted on the measured axis); (b) spend ~$10–15 to place GPT-5.5 / Gemini-3.1 / Opus-4.8 on
  our exact scale (all four benches have fully reproducible harnesses, so our runs would be methodology-comparable
  to the published older-gen columns — i.e. we could place current frontier on the same scale as R1 / o1 / Gemini-2.5).
  Recommendation: defer (a) now; spend on (b) only if/when the anchor lines become the launch's load-bearing visual.
- Contamination flag for any future self-run of AMO-Bench: its items+answers have been public on HF since Oct 2025.

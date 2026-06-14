# Leg A — between-model discrimination verdict (2026-06-15)

Probe inputs: 4 frontier anchors on the cheap-3 axes + 2 local models (gemma-4-e4b 7.5B = weak, qwen3-30b-a3b = mid) on suite-v1, Quick samples (≤50/bench). Math frontier = published reference (not measured). Machine-readable: `runs/probe-legA.json`. Harness: `python -m localbench.probe`.

## VERDICT: all 4 core axes discriminate — suite-v1 fixes v0's saturation failure
| axis | bench | verdict | anchor range | local range | floor→frontier spread | pt-biserial | weight |
|---|---|---|---|---|---|---|---|
| knowledge | supergpqa | **KEEP** | 0.60–0.71 | 0.20–0.38 | 0.51 | +0.54 | 0.33 |
| instruction-following | ifbench | **KEEP** | 0.72–0.92 | 0.36–0.52 | 0.56 | +0.59 | 0.36 |
| agentic | bfcl | **KEEP** | 0.84–0.96 | 0.48–0.98 | 0.50 | +0.50 | 0.32 |
| math | amo+olymmath | **KEEP\*** | published ~0.55–0.63 | 0.00–0.02 | huge (x-harness) | n/a | TBD |

\* The harness auto-flagged math `drop:frontier-flat`, but that is an **ARTIFACT**: anchors ran cheap-3 only (no measured math runs — math frontier is the published reference), so the harness saw only the locals (~0 = olympiad floor) + no anchor → defaulted to drop. The real signal: locals floor ~0 vs published frontier ~55–63% → a huge spread → **math is a real KEEP** (reference-ceiling axis). **HARNESS TODO:** teach the probe to read the published math reference (`docs/foundations/math-anchor-reference.md`) so math isn't mis-dropped.

## Reads
- None of the 3 measured axes are saturated at frontier (knowledge tops out 60–71%, not ~100) → genuine discrimination, positive point-biserial. **The rebuild works** (v0 had a 9B ≈ SOTA; here weak gemma sits far below frontier on every axis).
- Weights ≈ equal (~1/3 each), proportional to measured spread.
- Gemini 3.1 Pro = strongest anchor on all 3. qwen3-30b-a3b is surprisingly strong on agentic/bfcl (0.98, near-frontier).

## Caveats (Quick exploratory read — enrich later)
- Only 2 locals (thin spread). Add more for a fuller weight estimate.
- **27B (qwen3.6-27b) HUNG** mid-run: loaded 27.5 GB but 1% util on the tight 32 GB GPU at `-c 16384`. Retry with `-c 8192` or partial CPU offload.
- **Distill (reasoning model) pathologically slow** under `--lane answer-only` (LM Studio doesn't suppress its thinking). Local reasoning models need a reasoning-aware lane (or `/no_think` template handling).

## OPEN DESIGN — error rate in the final intelligence score (Michael, 2026-06-15)
> "should we include error rate in the algo that gives the final intelligence score — a weighted algo of combined scores incl. error rate → an absolute 0–100."

**My take: yes, but carefully, to avoid double-counting.**
- Separate the two failure modes the runner records: `n_errors` (API/runtime/timeout — usually the HARNESS's fault → **exclude** from a model-quality score) vs `n_extraction_failures` (the model emitted output but produced no parseable answer — garbage/refusal/format-break → the **model's** fault).
- Extraction-failures **already count as wrong** (they lower accuracy), so a naive `accuracy − error_rate` penalises twice.
- BUT a **clean wrong answer is more usable than garbage output** — and malformed output is precisely **the quant-degradation signal** (quants break JSON/stop-tokens/format, not raw capability). So a *modest, intentional* extra penalty for malformed output is justified.
- **Proposed headline:** `final = 100 × accuracy_composite × (1 − w · malformed_rate)`, with small `w` (~0.3–0.5), `malformed_rate` = model-fault extraction-failures / attempted (excluding infra errors). Surface **Intelligence (accuracy) + Reliability (1−malformed)** as transparent components (AA-style), not just one opaque number.
- Decide at **scoring-finalization** (after the suite axes/weights are locked) — not mid-probe.

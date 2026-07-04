# DISCRIMINATION CAMPAIGN — the gate that turns candidate axes into a measured headline

*2026-06-19. The costed, pre-registered, pure-GPU local-only run plan that replaces "assumed" with "measured"
for the widened foundation. NOTHING here runs without Michael's explicit GPU go ([[feedback-gpu-ask-first]]).
No API/anchor spend is required for promotion; anchors are optional later for a frontier line and saturation
reference. Cheapest-first, one model/server at a time, throughput-probed before each stage (the discipline that
prevents the 4× blowout). Reuses the existing probe tooling (`localbench` probe /
`probe/discrimination.py`, which computes per-axis floor→frontier spread + suggested weights).*

## Why this exists
Every discrimination number behind the foundation-widening is PUBLISHED / single-family (mostly Qwen), not
measured on our harness. Both red-teams named the same gate: measure on our harness before any axis goes
headline. This campaign is that gate. Its output decides, per axis: **drop / keep-as-profile / promote-to-headline**,
and sets headline weights by measured spread.

## The candidate axes + build status (what we're measuring)
| Axis | Bench | Build status | What the run must show to earn HEADLINE |
|---|---|---|---|
| Knowledge | MMLU-Pro (+ hardened Math/Physics slice) | built; harder slice = TODO (§A) | local spread AND optional frontier/reference NOT saturated |
| Instruction | IFBench (Allenai) | built | discriminates the LOCAL range (GPT-5.5 flag: maybe flat 8B 35% vs 32B 37%) |
| Math | mixed-difficulty rebuild | spec'd (MATH-REBUILD-SPEC); assemble = TODO (§B) | local band 10-70% AND monotonic local range |
| Coding-exec | BigCodeBench-Hard (opt-in Docker) | **BUILT + benchmark-ready** (`localbench code`) | local spread (target ~18→27→60%) + cross-family parse-fail <5% |
| Long-context | RULER-32k | built | local spread + serving-truncation clean |

## Model matrix (the spread — ≥3 local families/sizes on the 5090; anchors optional)
Local (5090, via `localbench run` / `localbench code`, reasoning-on, capped-thinking):
- **Qwen3.6**: 8B + 27B (already on the box). · **Gemma-4**: 12B (already on the box). · **Llama-3.x**: 8B
  (download). · one **1.5–4B** small model (download — the floor local).
Minimum promotion panel: at least 3 distinct LOCAL models that span family/size and can show a local-range slope;
preferred panel remains 3 families spanning ~1.5B→27B. *No-GPU prep:* download the 2 missing GGUFs
(network/disk, not GPU).
Optional later anchors (API, $-gated only if Michael asks): 1-2 frontier models (GPT-5.5 / Gemini) to draw a
frontier line and strengthen saturation checks. They are not required for promotion or weighting.

## Pre-registered decision rules (set BEFORE the run, per axis) — CONFIDENCE-BOUND
*Encoded + tested in `cli/src/localbench/probe/gates.py` (the oracle red-team, 2026-06-19, finding #4:
point estimates mislead at small N — a 2-model +/-5pp decision needs ~770 items, so a 148-item axis can
detect a big spread but cannot make a fine drop decision). The probe (`probe/discrimination.py`) applies these.*
- **Spread (CI-bound, not point):** KEEP + weight only if the **lower 95% bound** on the measured
  floor->frontier spread clears the keep threshold (0.15); DROP only if the **upper 95% bound** is below the
  drop threshold (0.05) AND the axis has >= 300 scored items (no fine drop on a tiny axis); otherwise
  **inconclusive** (need more items). Floor = weakest measured model overall; frontier = strongest measured
  model present (local OR anchor).
- **>= 3 LOCAL models to promote:** promotion needs at least 3 distinct local models so the axis separates local
  sizes/families, not just one local-vs-frontier gap. Ranked decisions use FULL item sets, never `--max-items`.
- **Saturation:** measured anchors, when present, are only a saturation/frontier check (>=2 anchors that do not
  separate by >3pp -> not headline). With NO anchors, use `reference_score` as a published ceiling if provided:
  strongest model within ~3pp of that ceiling is saturated/non-promotable. If neither anchors nor a published
  ceiling exist, skip saturation and rely on local spread + locals-floor.
- **Reference-anchored axes:** a published-ceiling-only axis is **triage** unless it saturates/drops; it is never
  weighted from the published ceiling alone.
- **Parse/extraction-failure on the UPPER bound:** gate on the upper 95% confidence bound of the failure
  rate, not the observed rate (0 failures in 58 items still leaves a ~6% upper bound). PLUS a **differential**
  gate: rates must be similar ACROSS families (a big gap = a formatting test, not a capability test). A breach
  excludes the axis from weighting.
- **Incremental information:** a candidate must add signal BEYOND Knowledge + Instruction, not merely
  correlate with overall ability. The probe surfaces a near-duplicate flag (|r| with the headline >= 0.98);
  the proper test is a partial-correlation / does-it-add-R^2 check on the campaign panel before weighting.
- **Headline weighting:** spread-proportional over the axes that PASS all gates; weakest-axis shown; promotion
  candidate->headline = a one-line registry weight edit (which moves the scorecard_id) + the drift test flows.

## Cost + sequencing (cheapest-first; STOP early on a kill)
- **Stage 0 — no GPU (in progress):** build the hardened knowledge slice (§A) + the math rebuild (§B); coding-exec
  is done; pin the bigcode image digest (a `docker pull`).
- **Stage 1 — throughput probe (≈free):** 20 items/axis on ONE local → real wall-clock + tokens/item → report
  the per-stage estimate BEFORE committing. (Coding-exec also measures per-task Docker exec time here.)
- **Stage 2 — local spread (5090, GPU-gated):** run >=3 locals (preferred 5 locals) × the axes. Slowest cost =
  reasoning-on long-context + the full sets; estimate from Stage 1. One model/server at a time; never two in parallel.
- **Stage 3 — analyze + lock:** run the probe → per-axis spread + parse-fail + suggested weights → apply the
  decision rules → lock the headline (registry weight edits) → update the methodology + site.
- **Optional later — frontier anchors (API, $-gated):** only if Michael wants a frontier line or stronger
  saturation evidence after the local-only analysis. Bring a throughput/token estimate first; no anchor spend is
  required for the base campaign.

## What's needed from Michael (the gates)
1. **GPU go** for Stages 1–2 (the local-only runs on the 5090).
2. OK to **download** the 2 missing local GGUFs (Llama-3.x-8B + a small model) and **`docker pull`** the
   bigcode image to digest-pin it (both no-GPU prep).
3. Optional later: **anchor-spend sign-off** only if Michael wants API frontier anchors after seeing the local-only
   probe results.

## The honest framing this protects
This campaign is the difference between "we built 5 plausible axes" and "we measured which ones actually
separate local sizes/families on our own harness." Until it runs, every widened axis (incl. coding-exec) stays
a **candidate**; the headline stays Knowledge + Instruction. The campaign is what lets the foundation widen on
evidence, not on papers — exactly what "don't launch on weak foundations" requires.

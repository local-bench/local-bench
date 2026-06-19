# DISCRIMINATION CAMPAIGN — the gate that turns candidate axes into a measured headline

*2026-06-19. The costed, pre-registered, GPU+$-gated run plan that replaces "assumed" with "measured" for
the widened foundation. NOTHING here runs without Michael's explicit GPU go + anchor-spend sign-off
([[feedback-gpu-ask-first]]). Cheapest-first, one model/server at a time, throughput-probed before each stage
(the discipline that prevents the 4× blowout). Reuses the existing probe tooling (`localbench` probe /
`probe/discrimination.py`, which computes per-axis floor→frontier spread + suggested weights).*

## Why this exists
Every discrimination number behind the foundation-widening is PUBLISHED / single-family (mostly Qwen), not
measured on our harness. Both red-teams named the same gate: measure on our harness before any axis goes
headline. This campaign is that gate. Its output decides, per axis: **drop / keep-as-profile / promote-to-headline**,
and sets headline weights by measured spread.

## The candidate axes + build status (what we're measuring)
| Axis | Bench | Build status | What the run must show to earn HEADLINE |
|---|---|---|---|
| Knowledge | MMLU-Pro (+ hardened Math/Physics slice) | built; harder slice = TODO (§A) | local spread AND frontier NOT saturated (>3pp top spread) |
| Instruction | IFBench (Allenai) | built | discriminates the LOCAL range (GPT-5.5 flag: maybe flat 8B 35% vs 32B 37%) |
| Math | mixed-difficulty rebuild | spec'd (MATH-REBUILD-SPEC); assemble = TODO (§B) | local band 10-70% AND monotonic local→frontier |
| Coding-exec | BigCodeBench-Hard (opt-in Docker) | **BUILT + benchmark-ready** (`localbench code`) | local spread (target ~18→27→60%) + cross-family parse-fail <5% |
| Long-context | RULER-32k | built | local spread + serving-truncation clean |

## Model matrix (the spread — ≥3 families × 3 sizes + ≥1 frontier anchor)
Local (5090, via `localbench run` / `localbench code`, reasoning-on, capped-thinking):
- **Qwen3.6**: 8B + 27B (already on the box). · **Gemma-4**: 12B (already on the box). · **Llama-3.x**: 8B
  (download). · one **1.5–4B** small model (download — the floor anchor).
That's 3 families spanning ~1.5B→27B. *No-GPU prep:* download the 2 missing GGUFs (network/disk, not GPU).
Frontier anchor (API, $-gated): **1 to start** (GPT-5.5 or Gemini), add a 2nd only if the first bunches.

## Pre-registered decision rules (set BEFORE the run, per axis)
- **Spread:** keep + weight ∝ measured floor→frontier spread if ≥15pp; drop / down-weight if <5pp (the
  existing probe thresholds). Floored (all locals ~0) or saturated (all ~ceiling incl. frontier) → not headline.
- **Local-range slope:** the axis must separate the LOCAL sizes (not just local-vs-frontier) — directly tests
  GPT-5.5's IFBench-might-be-flat concern.
- **Cross-family parse/extraction-failure < 5%** on any family (Gemini's systemic risk: reasoning-on CoT can
  make answer-extraction fail at different rates across families → a formatting test, not a capability test).
  Measured as no-answer/extraction-failure rate per family.
- **Headline weighting:** spread-proportional over the axes that pass; weakest-axis shown; one signed manifest
  (the registry). Promote candidate→headline = a one-line registry weight edit + the drift test flows.

## Cost + sequencing (cheapest-first; STOP early on a kill)
- **Stage 0 — no GPU (in progress):** build the hardened knowledge slice (§A) + the math rebuild (§B); coding-exec
  is done; pin the bigcode image digest (a `docker pull`).
- **Stage 1 — throughput probe (≈free):** 20 items/axis on ONE local → real wall-clock + tokens/item → report
  the per-stage estimate BEFORE committing. (Coding-exec also measures per-task Docker exec time here.)
- **Stage 2 — local spread (5090, GPU-gated):** run the 5 locals × the axes. Slowest cost = reasoning-on
  long-context + the full sets; estimate from Stage 1. One model/server at a time; never two in parallel.
- **Stage 3 — frontier anchor (API, $-gated):** 1 anchor across the axes. Estimate ≈ **$15–40** for one anchor
  over ~1,150 items at reasoning-on token rates (knowledge 400 + IFBench 294 + math ~150 + coding 148 + RULER
  60); coding-exec anchor cost = generation only (execution is local Docker, free). Confirm with a 20-item probe first.
- **Stage 4 — analyze + lock:** run the probe → per-axis spread + parse-fail + suggested weights → apply the
  decision rules → lock the headline (registry weight edits) → update the methodology + site.

## What's needed from Michael (the gates)
1. **GPU go** for Stages 1–2 (the local runs on the 5090).
2. **Anchor-spend sign-off** for Stage 3 (the ~$15–40 frontier anchor; I bring the throughput-measured estimate first).
3. OK to **download** the 2 missing local GGUFs (Llama-3.x-8B + a small model) and **`docker pull`** the
   bigcode image to digest-pin it (both no-GPU prep).

## The honest framing this protects
This campaign is the difference between "we built 5 plausible axes" and "we measured which ones actually
separate local from frontier on our own harness." Until it runs, every widened axis (incl. coding-exec) stays
a **candidate**; the headline stays Knowledge + Instruction. The campaign is what lets the foundation widen on
evidence, not on papers — exactly what "don't launch on weak foundations" requires.

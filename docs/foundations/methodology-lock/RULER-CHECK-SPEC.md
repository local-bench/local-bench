# RULER-CHECK SPEC — confirm long-context discrimination (open item #2)

*2026-06-19. Closes the DESIGN of the RULER local-discrimination check without running a benchmark
(per Michael's "don't run any benchmarks" constraint). The run itself is **sign-off-gated and DEFERRED**.
Until it confirms local→frontier spread, Long-Context stays a **candidate** (composite weight 0).*

## Why it's a candidate, not headline (yet)
RULER-32k is a genuine local pain point that few public leaderboards cover, and both red-teams agreed it
*should* discriminate — but local-bench has **not yet measured** that it discriminates across local→frontier
on OUR harness. The DECISION (Michael's sign-off) admitted RULER as a candidate explicitly: "Stage 2
discrimination data decides keep/weight." We will not weight it into the headline on an assumption — the
recurring lesson this project keeps relearning is *assumed ≠ measured discrimination*.

## What's already built (no new code)
- `ruler_32k.jsonl` (60 items), generator + truncation assertion (task #40), vendored from NVIDIA/RULER
  (Apache-2.0), itemset hash pinned in `suite.json` + `itemsets.lock.json`.
- The RULER scorer + the serving-truncation guard (a too-small server context silently truncates the 32k
  prompt → the run must FAIL loudly, not score a truncated context as wrong; already tested).
- Decoding: `max_tokens` 4096 (needle-style answers are short), reasoning-on lane, f16 KV.

## The gate (DEFERRED — sign-off-gated, NOT this pass)
Pre-registered, cheapest-first, one model/server at a time, throughput-probed before committing:
1. **Serving sanity FIRST.** Confirm the local server is configured for ≥32k context with f16 KV and
   ≥12k tokens/slot; the truncation assertion must pass (no silent context truncation). A misconfigured
   server invalidates the whole axis — verify before spending the run.
2. Run RULER-32k reasoning-on on **2–3 locals spanning capability** (e.g. an 8B, Gemma-4-12B, Qwen3.6-27B)
   + **1 frontier anchor** ($-gated).
3. **PASS if the axis SEPARATES** — i.e. local scores spread (weak local clearly below strong local) AND
   frontier clearly above locals, with non-overlapping CIs at the chosen item count. **FAIL if locals bunch**
   (all floored or all saturated) — then RULER stays experimental/parked, not headline.
4. **Item count:** 60 may be too few for tight CIs at 32k; if step-3 CIs overlap only marginally, expand the
   itemset (the generator supports more) before concluding. Long-context items are slow — report the
   throughput-measured wall-clock per model BEFORE committing (Gemini's red-team flagged users abort on
   slow long-context; we must know the real cost).

## If it passes
Promote Long-Context: candidate → headline; set its weight by observed spread (spread-proportional, capped);
the registry edit (`localbench.scoring.axes`) is one line and the drift test + all composite math flow from
it. If it fails to separate, it remains a displayed-but-unweighted profile axis (like Agentic/Coding), and
the model page can still show a long-context number as colour, not a headline claim.

## Cost
Local GPU time for 2–3 locals (long-context = slow; measure first) + one small frontier anchor run. Nothing
runs until Michael authorizes the stage; estimates reported before each model per the campaign discipline.

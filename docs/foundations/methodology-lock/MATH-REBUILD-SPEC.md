# MATH-REBUILD SPEC — mixed-difficulty math axis (open item #1)

*2026-06-19. Closes the DESIGN of the math rebuild without running a benchmark (per Michael's
"don't run any benchmarks" constraint). Item-set assembly + the local-band validation run are
**sign-off-gated and DEFERRED**. Until validated, Math stays a **candidate** (composite weight 0).*

## Problem
The current Math axis = `amo` (39) + `olymmath_hard` (100), both olympiad-hard. On local models they
floor at ~0% (verified on the Gemma/Qwen ladders), so Math cannot enter the headline composite: a floored
axis adds noise, not signal, and silently dilutes the headline. It also can't separate a 7B from a 70B if
both score ~0.

## Goal
A **mixed-difficulty** math set that spans easy → hard so the axis **discriminates across the whole
local→frontier range**, with a **local accuracy band of ~10–70%** (not floored, not saturated). Pure
MATH-500 risks saturating the frontier; pure OlymMATH/AMO floors locals — so blend.

## Composition (target ~150–200 items, 3 difficulty strata)
| Stratum | Target local acc | Source (licensing-clean) | Count |
|---|---|---|---|
| Easy | 70–95% | **generated-math** (our templated engine, `suite/v0` genmath lineage) — arithmetic, linear/quadratic, basic algebra, randomized parameters | ~60 |
| Medium | 30–70% | **generated-math** multi-step (systems, sequences, counting, geometry templates) + optional MATH levels 1–3 IF license confirmed | ~60 |
| Hard | 0–30% | existing `olymmath_hard` + `amo` (already vetted, frontier-separating top end) | ~50 |

- **Prefer generated + existing-hard** to stay fully licensing-clean AND contamination-resistant (templated
  variants rot answer keys). Only add a static set (e.g. MATH levels 1–3) if a clean license is confirmed;
  otherwise the generated engine covers easy/medium.
- Difficulty is a STRATUM LABEL (for subgroup reporting), NOT a separate scored lane — difficulty-stratified
  *scoring* stays retired (both red-teams); we stratify only to compose a discriminating spread.

## Scorer (already built — no new code)
The symbolic verifier (`math_symbolic.py`, sympy/math-verify, task #36) gates correctness for all three
strata, with the truncation guard (`finish_reason == "length"` disables the bare-number fallback). The
generated engine already emits canonical answers; olymmath/amo answers are vetted.

## Manifest + registry wiring (when assembled)
- Add the assembled itemset(s) to `suite/v1/suite.json` under the math axis with `item_count` + `sha256`
  (+ `itemsets.lock.json` provenance), keeping Math = ONE pooled axis (generated + olymmath + amo).
- The axis MEMBERSHIP in `suite.json` must match `localbench.scoring.axes.AXES` (the drift-gate test). If a
  new bench id is introduced (e.g. `math_mixed`), add it to the registry's `math` axis `benches`.

## Validation run (DEFERRED — sign-off-gated, NOT this pass)
Pre-registered pass/fail, cheapest-first, one model/server at a time, throughput-probed before committing:
1. Run the assembled set reasoning-on (budget 8192, f16 KV) on **one local** (Gemma-4-12B or Qwen3.6-27B).
   **PASS if local pooled accuracy lands in 10–70%** (not floored/saturated) with a spread across strata.
2. Run **one frontier anchor** ($-gated) on the same set. **PASS if frontier > local by a clear margin**
   (the axis separates local from frontier).
3. If both pass → **promote Math: candidate → headline**, set its weight by observed spread
   (spread-proportional, capped), update the registry (one-line weight edit) — the drift test + all
   composite math then flows automatically. If it floors/saturates → re-balance strata and re-run.

Estimated cost: local GPU time only for step 1; step 2 is a single small frontier anchor run (tens of items)
— report the throughput-measured wall-clock + $ before running, per the campaign discipline.

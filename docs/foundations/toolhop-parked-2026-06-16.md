# ToolHop parked as a scored rung — decision record (2026-06-16)

## Decision
**ToolHop is removed from the scored suite** (reverted in `5e1099b`). **BFCL multi-turn is the agentic upgrade.**
The full ToolHop infrastructure (scorer + multi-hop confined executor + builder + loosen/verified-only fix
approach) is preserved at commit **`f0ce8cf`** and is recoverable (un-revert) for a future attempt.

## Why (a validity failure, not a hard benchmark)
A judge-free, distance-to-frontier benchmark needs **known-solvable items** — else the score conflates model
weakness with harness/item invalidity. ToolHop ships **no gold call-trace**, so our builder must DERIVE one per
item and verify it reproduces the gold answer under confinement:
- First build: 100 items, but **78 were dead/unsolvable** under confinement → floored every model (the SWE-bench
  failure mode we set out to avoid). Caught in review (only 21/22 gold-trace items self-scored).
- After **loosening** the confined-exec allowlist to safe-compute libs (numpy/sympy/dateutil/…): only **42** items
  verified-solvable across the 995-row dataset. The bottleneck is **trace-derivation, not imports** — more
  loosening won't move it.
- Those 42 are a **biased subset** (selected for confinement-friendliness + trace-derivability, which correlates
  with simpler tool paths / less real multi-hop planning), so they may **not preserve ToolHop's published
  discrimination gradient** (7B 11% → 32B 20% → GPT-4o 49% was measured on the full set). Value is small AND a
  non-representative slice — not headline-rung material.

## Red-team (GPT-5.5 xhigh) — AGREE-WITH-CAVEATS
1. Parking ToolHop as a scored rung is correct; the dead-item build is a validity failure, not recoverable.
2. The "tools-run-but-trace-unverified" larger pool is **worse** — re-accepts dead-item risk + makes failures
   ambiguous (planning error vs trace-derivation vs backend mismatch vs confinement artifact), undercutting the
   judge-free premise.
3. **Don't fully discard** — keep the 42 verified items + infra as an experimental, non-ranking diagnostic / to
   guide a future **trace-authoring** effort. (Preserved at `f0ce8cf`.)
4. **Honest messaging**: BFCL multi-turn is a *harder stateful/tool-call* benchmark — NOT a *multi-hop planning*
   benchmark. Dropping ToolHop leaves a real capability gap (multi-step planning over tool observations ≠
   multi-turn function-calling against fixed audited backends). Do not overclaim.

## The scored agentic axis now
`agentic = [bfcl (single-turn AST, down-weight = saturated floor), bfcl_multi_turn (harder rung; small ~35% vs
frontier ~75%; confined, judge-free)]`. This **de-saturates** the agentic axis (the goal) but is honestly a
"harder tool-call" axis, not "agentic planning."
- **Open: the multi-hop PLANNING gap** — revisit ToolHop only with a better gold-trace-derivation path (e.g.
  author traces, or use ToolHop's own reference mechanism), or find another local-runnable, judge-free,
  verified-solvable multi-hop bench.
- **Still open #63**: the Agentic axis pools `bfcl`(300) + `bfcl_multi_turn`(100) item-weighted → the saturated
  AST rung carries ~75%. The discrimination probe must reweight by measured spread (or shrink/down-weight AST).

## Net
suite-v1 agentic upgrade = BFCL multi-turn (done, verified, 524 tests green). ToolHop = parked/experimental,
fully recoverable. Honest scope, no dead items, judge-free premise intact.

# Season-2 Agentic/Tool-Use Axis — Design & Implementation Anchor

**Status:** APPROVED (structure) — Michael blessed Option D + full autonomous authority 2026-07-12.
**Owner:** Claude (orchestrator) → codex GPT-5.6-sol builds under adversarial QA.
**Scope:** local-bench 0.4.0 season-2 methodology. Multi-chat undertaking — THIS DOC IS THE ANCHOR.
**Priority:** AFTER the two in-flight critical items — gemma-4-31b landing + B2a certification.

> Resume rule: read this doc first, then check the "Progress log" at the bottom for where we are.

---

## 1. Goal & why now

Fix the agentic axis before public contributions open (weight changes re-rank contributors, so
the cheapest time is now, while the only board rows are our own seed set). Adopt the oracle's
red-team (GPT-5.5 Pro) as sharpened by ground-truth + a second code-grounded consult
(GPT-5.6-sol xhigh). Launch season-2 as THE public-contribution methodology.

**North-star constraint (Michael):** the whole product is a **robust, repeatable, one-line CLI
pull** — turnkey start→finish for anyone benchmarking + submitting. Every season-2 change MUST be
invisible to that one command. The 0.4.0 dogfood canary (a clean end-to-end public-CLI run on a
real model) MUST exercise the FULL tool-use macro-axis, not just the easy axes, and is the
release/announce gate.

## 2. Ground-truth (verified in code, 2026-07-12) — what EXISTS vs GREENFIELD

- **Axis registry:** single source `cli/src/localbench/scoring/axes.py` `AXES`. Current headline
  weights (sum 1.0): agentic **0.40** (bench `appworld_c`), knowledge 0.15, instruction_following
  0.15, coding 0.15, tool_calling **0.10** (bench `tc_json_v1`), math 0.05, long_context 0.0.
  Editorial label "index-v3.0". A weight edit auto-cascades `registry_digest` → `scorecard_id` →
  `suite_manifest_sha256` (`scoring/scorecard.py`).
- **AppWorld already = Test-Normal + TGC:** `agentic_exec/funnel.py` scores ONLY `test_normal`
  (96-task seeded stratified draw from 168); metric is binary Task-Goal-Completion from native
  `world.evaluate()` (`agentic_exec/env_host.py:183`). So the oracle's "switch to Test-N + use
  TGC" is ALREADY TRUE. Our never-shipped "d1-stratify" idea is simply DROPPED. Test-Challenge is
  greenfield (docs only). Difficulty labels feed sampling stratification only, not scored output.
- **BFCL already BUILT (orphaned/unweighted):** scorers `scorers/bfcl/` (single-turn AST/exec) +
  `scorers/bfcl_multi_turn/` (backend/executor/sandbox/checker). Itemsets `suite/v1/bfcl.jsonl`
  (300) + `suite/v1/bfcl_multi_turn.jsonl` (100 = **50 base + 50 long_context**, each item has a
  `category` field; builder `suite/build_v1_bfcl_multi_turn.py` `_stratified_sample` selects
  exactly 50/50 — splitting is trivial). Vendored bfcl-eval **BFCL v4** (not v3), Apache-2.0,
  scorer versions hashed. NOT on any axis today.
- **tc_json_v1 is BUILT FROM the BFCL rows** (`cli/scripts/build_tc_json_v1.py:34`) + 30
  hand-authored common/no-tool cases. Its distinct value is strict JSON-envelope/schema
  conformance (`scorers/tc_json_v1/scorer.py:27`), NOT independent content. → tc_json ⟂ BFCL is
  FALSE; they share source data (non-independent → double-count risk if both weighted).
- **toolhop is REMOVED/parked** (`docs/foundations/toolhop-parked-2026-06-16.md`); scorer dir has
  no implementation. Off the table.
- **Composite mechanics:** plain chance-corrected item-weighted mean. IMPORTANT: the axis
  implementation **item-pools benches** (`scoring/board_scoring.py:442`) — so a macro-axis of
  "AppWorld 96 + base 50" would weight by item count (66/34), NOT an intended 50/50. Deliberate
  internal weighting REQUIRES an explicit **bench-normalized macro-weighting** change.
- **Season plumbing already exists:** dual scale shipped — `composite_full` (index-v3.0,
  agentic-led) vs `composite_static` (static-suite-v2, 5-axis no-agentic); coverage-profile
  machinery (`suite_release.py` `COVERAGE_PROFILES`, incl. a `rankable=False` diagnostic profile);
  axis status `measured|not_measured|generated_unverified` (`scoring/axis_status.py`); mature
  "diagnostic / unweighted" display vocabulary. NO literal "season" concept yet — season-2 is a
  NEW coverage profile + NEW editorial label on THIS machinery, additive to v1.

## 3. The decision — Option D (two-model converged)

**One capped 20% "tool-use" macro-axis with weighted sub-facets** (replaces agentic 0.40 +
tool_calling 0.10):

| Sub-facet | Bench | Construct | Initial weight (calibration-tunable) |
|---|---|---|---|
| Agentic | AppWorld `appworld_c` (test_normal TGC, 96) | observation-conditioned iterative agency | 0.50 |
| Multi-turn tool control | BFCL multi-turn **base** (50) | stateful sequencing (single-shot trace) | 0.35 |
| Call formatting | `tc_json_v1` | strict JSON-envelope/schema conformance | 0.15 |

- Macro-axis total composite weight = **0.20** (down from 40% agentic + 10% tool_calling = 50%).
- **Diagnostics, published but UNWEIGHTED:** BFCL single-turn (300; overlaps tc_json), BFCL
  multi-turn **long_context** (50; conflates context-capacity/KV-cache with reasoning), AppWorld
  Test-C sentinel (future), per-difficulty AppWorld ASR, all existing agentic rate diagnostics.
- **Naming:** call the axis **"tool-use"** (AppWorld is the agentic facet *inside* it) — honest,
  since BFCL-multi-turn is stateful sequencing, not true interactive agency (it emits the whole
  turn trace in one generation — codex `bfcl_multi_turn/_prompt.py`, `_executor.py`).

**Why D over A/B/C:** caps total tool-use influence at 20% *by construction* (the double-count
fix), keeps the three genuinely-distinct facets visible, weights the richest (AppWorld) highest.
Codex's own finding that tc_json is BUILT FROM BFCL rows breaks the A-vs-D tie toward D: a
separate top-level tc_json axis would be a non-independent component double-counting BFCL.

**Validation gate is NOT a correlation cutoff.** Both models rejected ">0.85 → merge." Use
reliability (split-half), residual/incremental discrimination, disagreement cases, and rank
sensitivity to (a) finalize the internal sub-weights and (b) decide whether tc_json_v1 stays a
weighted facet or drops to diagnostic. Placeholders 0.50/0.35/0.15 hold until calibration.

## 4. Sub-projects (decomposition + build order)

Each is an independent unit with its own codex build → my QA → xhigh reverify → SHIP.

- **S2-1 · Macro-axis registry + bench-normalized weighting.** Introduce a hierarchical
  macro-axis in `axes.py` (or a thin macro-axis layer) with explicit per-sub-facet weights;
  implement bench-normalized weighting so sub-weights are honored regardless of item counts
  (fixes the 66/34 item-pool trap); set macro-axis composite weight 0.20; renormalize remaining
  axes to 0.80. NEW `scorecard_id`/shas expected (additive). *No GPU.*
- **S2-2 · BFCL wiring + itemset split.** Split `bfcl_multi_turn.jsonl` scoring into base
  (weighted) vs long_context (diagnostic) using the existing `category`; wire BFCL-multi-turn-base
  into the macro-axis; register single-turn BFCL + long_context as unweighted diagnostics. Keep
  vendored file as-is (one hashed artifact); split analytically. *No GPU.*
- **S2-3 · Season-2 coverage profile + editorial label + bridge.** New `CoverageProfile`
  (`suite-v2-…` or `full-exec-6axis-v2`) alongside the existing two; new editorial label
  (e.g. "index-v4.0"); season-1→2 bridge table; re-run anchor rows under S2; forbid cross-season
  composite comparison in UI. Additive — v1 profiles/shas untouched. *No GPU (uses existing runs
  where possible; anchors may need re-scoring, not re-running, since axis math is post-hoc).*
- **S2-4 · Calibration & validation season.** Panel of 10-16 family-diverse 7-32B quants; gates:
  ≤25% of panel at floor/ceiling per weighted facet, IQR ≥~10pts, scenario-level bootstrap,
  split-half ≥~0.8, runtime measured on a slow 32B (not a fast 7B). Reuse already-scored models
  first; only run NEW models to fill family/quant gaps. Finalizes sub-weights + tc_json
  keep/demote. *GPU — sequenced AFTER gemma landing + variant-ladder season.*
- **S2-5 · Website update (FINAL step).** Methodology page (`web/app/methodology/page.tsx`) new
  editorial label + macro-axis explanation + sub-facet breakdown + diagnostics section; board
  shows the season-2 macro-axis; dual-scale/bridge surfaced; diagnostics displayed but never
  ranked. Via gated landing + `git push deploy` on a clean gate. Public contributions open on S2.

**Build order:** S2-1 → S2-2 → S2-3 (code, no GPU, can proceed once gemma frees the box for
suite runs) → S2-4 (GPU calibration, after ladder season) → finalize weights → S2-5 (website) →
0.4.0 dogfood canary (turnkey end-to-end, exercises full macro-axis) = release/announce gate.

## 5. Turnkey / hermetic acceptance criteria (apply to every sub-project)

- Zero user-visible setup: one CLI command still pulls GGUF → runs all axes (incl. the heavier
  macro-axis) → submits. No repo clone, no API keys, no backend config, no "set up BFCL".
- Hermetic/offline: BFCL runs network-disabled; explicit category allowlist; block any
  network-capable category (e.g. web_search/SerpAPI). Vendored+hashed snapshot only; never
  "install latest BFCL" at eval time.
- Reproducible: identical pass/fail under the frozen environment; full traces + hashes in results.
- Fits 17-24h single-GPU budget alongside the other axes (measure on a slow 32B).

## 6. Testing strategy

- Unit: macro-axis weighting math (bench-normalized; sub-weights honored under skewed item
  counts); base/long_context split; diagnostic-not-ranked invariant; renormalization to 0.80.
- Identity: new profile → new `scorecard_id`/shas; v1 profiles/shas byte-unchanged (regression).
- Integration: a full run produces the macro-axis composite + all diagnostics; board reflects it;
  season-1 rows still render under v1 label; bridge table correct.
- Adversarial (xhigh reverify each sub-project): double-count leakage, diagnostic re-badging a
  row, item-pool weighting regressions, non-hermetic BFCL path, cross-season comparison leak.
- Suites run SEQUENTIALLY (pytest then vitest), never concurrently with a GPU/agentic run
  (process-exhaustion lesson).

## 7. Open items resolved by calibration (NOT by guesswork)

- Final internal sub-weights (start 0.50/0.35/0.15).
- tc_json_v1: weighted small facet vs demote to diagnostic (it's BFCL-derived).
- Whether AppWorld Test-C sentinel / per-difficulty ASR graduate from diagnostic.

## 8. Guardrails (standing)

Adversarial loop (codex build → independent pytest+vitest → xhigh reverify → maintainer
disposition → SHIP). GROUND-TRUTH (every number verified vs our harness before freeze; fabricate
= STOP). Additive only — never mutate v1 shas c4098df8…f468 / 4e240f8c…c61d64. Board only via
gated landing; deploy needs clean gate. One codex build at a time. Never commit scratchpad/.
Season-2 is the LAUNCH methodology; announce (#21) gates on the dogfood canary being green.

---

## 9. S2-1 design-review outcome (codex read-only consult, reviewed by orchestrator 2026-07-12)

Codex's proposal APPROVED with refinements. Two prerequisites/blast-radius findings materially
change the plan:

**NEW PREREQUISITE — S2-0 · Freeze v1 profile identity (MUST precede any registry change).**
The manifest builder uses the LIVE scorecard + LIVE axis membership for every non-legacy profile
(`suite_release.py:115`), and `cli/scripts/build_6axis_suite_release.py:58` deletes+rebuilds the
v1 dirs. So editing the `AXES` singleton would change v1's *computed* identity → v1 shas break.
Fix: generalize the existing frozen-legacy snapshot pattern (`suite_release.py:277`) into
profile-specific frozen scoring snapshots — freeze the two locked v1 profiles' axis membership,
registry_digest, scorecard_id, scorer_versions — and stop the release script from regenerating
v1. Regression test: rebuilding both v1 profiles still reproduces `c4098…f468` / `4e240…c61d64`
(extend `cli/tests/test_suite_release_manifest.py:133`). Without S2-0, "additive" is a fiction.

**S2-1 refined (facets on Axis):** add optional `facets: tuple[FacetSpec,...]=()` to the `Axis`
dataclass; `FacetSpec{key, bench, weight, selector}` (selector e.g. `category=="multi_turn_base"`,
grounded at `build_v1_bfcl_multi_turn.py:22,88`). Keep `Axis.benches` as the flat compat surface
(helpers at `axes.py:37,131,186` flatten it). Define `tool_use` = benches
`(appworld_c, bfcl_multi_turn, tc_json_v1)` + facets 0.50/0.35/0.15. Existing axes leave
`facets=()` → keep item-pooling. Extend `_validate()`: unique facet keys, positive weights,
selectors reference an axis bench, facet-sum==1.0. (Rejected: parallel weight dicts (drift) and
synthetic bench names (won't match registered scorer).)

**Item-pool fix — 4-place blast radius (must stay in parity or scores diverge):**
`board_scoring.py:390/:474`, `web/build_data_axes.py:120/:166`, normal-run `_scoring.py:234`,
submission projection `foundation_scores.py:101`. One registry-owned facet-sample helper (applies
the BFCL selector) + `bootstrap.composite_ci` (already normalizes declared bench weights);
`_source_weights_for_composite` assigns `axis_weight × facet_weight`, keeping count-allocation only
for facet-less axes. Weighted completeness FAILS CLOSED: any of the 3 facets absent → omit
`tool_use` → `composite_full=None` (existing strict check `board_scoring.py:494`). Parity test
across all 4 paths.

**Weight math:** `tool_use .20 + knowledge .24 + instruction_following .24 + coding .24 + math .08
= 1.00` (retained four = old .15/.15/.15/.05 × 1.6). Static scale: FREEZE `static-suite-v2` (it
includes tool_calling); if a season-2 static comparator is kept, add `static-suite-v3` over the
four non-tool axes at .30/.30/.30/.10.

**Diagnostics:** no `diagnostic` AxisRole exists (only headline/candidate/experimental,
`axes.py:34`; axis_status describes measurement not ranking). Use role=`experimental`, weight 0,
+ `rankable=False` presentation. Single-turn BFCL + BFCL `multi_turn_long_context` NEVER enter
weighted-facet completeness or the composite.

**Identity:** deliberate `SCORECARD_VERSION` bump + facets/weights → new v2 scorecard/manifest;
regression-lock `suite/release-pairs.expected.json:5,11`.

**Web-coupling DECISION (orchestrator):** web imports LIVE registry weights
(`build_data_axes.py:20`) but hardcodes `index-v3.0` (`build_data.py:67`). To keep the website on
v1 until S2-5, S2-0..S2-4 builds MUST NOT regenerate or deploy web data — the site stays on v1
until the S2-5 flip. (Alternative — profile-selective web consumption — deferred to S2-5.)

**Naming:** the v2 headline set is FIVE macro-axes (tool_use, knowledge, instruction_following,
coding, math; long_context stays 0-weight) — so name the profile `full-exec-tooluse-5axis-v2`
(not "6axis"); editorial label `index-v4.0`. Finalize at build.

**Revised build order:** S2-0 (freeze v1 identity) → S2-1 (facets + 4-place weighting + v2
profile) → S2-2 (BFCL split/wiring) → S2-3 (bridge/editorial) → S2-4 (calibration GPU, after
ladder) → S2-5 (website flip = FINAL) → 0.4.0 dogfood canary = gate.

## 10. S2-1 build STOP → selector replaced by BENCH SPLIT (2026-07-12, codex ground-truth STOP)

S2-1 build (codex) STOPPED correctly: the planned per-item `category==multi_turn_base` facet
SELECTOR cannot be honored uniformly. board_scoring has item records (can filter), but
`_scoring.composite()` (:234) and `foundation_scores._axis_aggregate()` (:101) receive only
pre-aggregated `BenchAggregate` values (category metadata already lost); the lossy conversion is in
`submissions/projection.py:225` + `foundation.py:475` + `orchestrate.py:790` (outside permitted
scope). Approximating with the full 100-item BFCL aggregate would wrongly weight the 50 long_context
items. v1 shas confirmed still frozen; no changes made.

**RESOLUTION (orchestrator decision — implementation, not product): BENCH SPLIT, not selector.**
Split `bfcl_multi_turn` (100) into TWO first-class benches for v2: `bfcl_multi_turn_base` (50) +
`bfcl_multi_turn_long_context` (50), via the suite build (items already carry `category`; builder
already selects 50/50). Then the tool_use facet weights whole-bench `bfcl_multi_turn_base` (0.35),
`bfcl_multi_turn_long_context` becomes an experimental wt-0 diagnostic bench, and ALL scoring paths
use uniform whole-bench aggregates — NO item selector, NO facet metadata threaded through the
submission pipeline. Additive: v1 stays frozen on the original 100-item `bfcl_multi_turn` bench; v2
references the two split benches. Supersedes §9's `FacetSpec.selector` (facets now bench-only:
`FacetSpec{key,bench,weight}`, no selector). Revised S2-1 scope adds: suite build emits the two v2
benches + itemsets; bench registration + scorer_versions for both; v2 coverage profile references
them. Everything else in §9 (macro-axis, bench-normalized weighting across the 3 CLI sites,
fail-closed, weight math .20/.24/.24/.24/.08, web deferred to S2-5) stands.

## 11. Bench-split design consult review (2026-07-12) + S2-1 STAGING

Consult (codex read-only) confirms bench-split is viable + additive. Approach:
- New `suite/build_v2_bfcl_multi_turn.py` + self-contained `suite/v2/**`; v1 (`suite/v1/**`, both v1
  profiles, `_V1_EXEC_SCORING_SNAPSHOT`, `_FROZEN_PROFILE_SCORING` suite_release.py:122, `FROZEN_BUNDLES`,
  pins c4098df8/4e240f8c) all UNTOUCHED. v2 profile `full-exec-tooluse-5axis-v2` built from suite/v2
  (release id `suite-v2-…`) uses live registry.
- 3 scorer keys `bfcl_multi_turn` / `bfcl_multi_turn_base` / `bfcl_multi_turn_long_context` — same
  impl + version "1", but each needs its OWN registry key (drift guard per-bench, scorecard.py:46,
  test_scorecard.py:154). No item selector anywhere; whole-bench aggregates in _scoring/foundation/board.
- Also touches: `_suite.py`, `signed_score.py` (zero baselines for new benches),
  `benchmark_registry.py` (add base to defaults; long_context+single-turn bfcl diagnostic/opt-in).

Two wrinkles + my resolutions (implementation-level):
1. **Macro-axis spans 2 execution lanes** (appworld_c out-of-band/agentic-exec vs bfcl/tc_json HTTP);
   `BenchmarkModule` assumes one lane per module (benchmark_registry.py:11). Resolution: the axis is a
   SCORING grouping — keep execution modules PER-BENCH (each bench its own lane/module); generalize the
   registry's axis→lane assumption minimally only if it hard-blocks. Do NOT force the axis single-lane.
2. **Diagnostics profile policy**: include wt0 diagnostics (long_context, single-turn bfcl) as
   role=experimental MEASURED benches in the v2 profile but weight-0 (measured+shown, never ranked).

**S2-1 STAGED into 2 sub-builds** (large; each independently pytest-verifiable):
- **S2-1a** = bench-split foundation: suite/v2 + build_v2_bfcl_multi_turn.py + the 2 split benches +
  3rd retained + 3 scorer keys + benchmark_registry defaults + signed_score baselines + tests (benches
  build + self-score; v1 shas UNTOUCHED). NO axis/profile/weighting yet.
- **S2-1b** = macro-axis: tool_use facets (appworld_c .50 + bfcl_multi_turn_base .35 + tc_json_v1 .15
  @ 0.20) + bench-normalized weighting (board_scoring/_scoring/foundation_scores) + fail-closed +
  v2 coverage profile + weights .20/.24/.24/.24/.08 + CLI test updates. Web deferred to S2-5.

## Progress log
- 2026-07-12: Ground-truth mapped (Explore). Oracle + codex two-model panel → Option D. Michael
  approved structure + FULL autonomous authority. Design doc written + committed 812bece.
- 2026-07-12: S2-1 read-only design consult (codex GPT-5.6-sol xhigh) done + reviewed → §9.
  NEW prerequisite S2-0 (freeze v1 identity) identified; item-pool fix is 4-place; web stays on
  v1 until S2-5. Plan refined. NEXT: after gemma landing + B2a cert free the box, dispatch S2-0
  BUILD (codex, additive, suites sequential) → my QA → xhigh reverify → SHIP; then S2-1 onward.
- 2026-07-17: OWNER DIRECTIVE (Michael) — the macro-axis is renamed to an agentic-named axis and
  its composite weight rises to 25%. Implemented on branch `feat/agentic-axis-reweight` as
  **index-v4.1** (scorecard-v6): display label "Tool Use" → "Agentic" (ALL structural keys
  unchanged — axis/web key `tool_use`, facet keys, bench ids, profile id); weights
  25/22.5/22.5/22.5/7.5 (the +5pp deducted proportionally from Knowledge/Instruction/Coding/Math,
  a 15/16 scale; exact sum 1.0; facet split 10/17-7/17 unchanged). index-v4.0 rows are a
  distinct historical scale and must be re-scored (board rebuild) to carry v4.1. BLOCKER for
  community submissions: the frozen accepted-projection v2 contract enum admits only
  index-v3.0/index-v4.0 → v4.1 submissions need a deliberate contract rev (owner-gated,
  separate change). Landing checklist: scratchpad/agentic-reweight-validation-checklist.md
  (worktree, uncommitted).

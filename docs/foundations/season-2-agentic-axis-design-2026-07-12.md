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

## Progress log
- 2026-07-12: Ground-truth mapped (Explore). Oracle + codex two-model panel → Option D. Michael
  approved structure + full autonomous authority. Design doc written (this file). NEXT: writing-
  plans → S2-1 codex build, sequenced behind gemma landing + B2a cert.

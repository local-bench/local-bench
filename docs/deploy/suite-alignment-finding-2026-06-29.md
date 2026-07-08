# Suite-alignment finding — 2026-06-29

**Status:** investigation result, no code/contract changed. Written as an input to the
**step-3 submission-slice oracle red-team** (the key architectural gate in
`project-local-bench-site-submission-plan`). Resolves the plan's open item
"confirm site `core-text-v1` == v2.1 5-axis suite" — answer: **it is not**, and that
gap shapes what a first published board row can mean.

## TL;DR

There are **three different "suites"** in play, covering **different axis subsets**, with
**different hashes**. None of them, run on a plain OpenAI-compatible endpoint, produces a
complete v2.1 headline index:

| Artifact | Axes it can produce on a plain endpoint | Notably missing | Weight covered |
|---|---|---|---|
| Canonical headline (`scoring/axes.py`) | knowledge, instruction, tool_calling, coding, **agentic** | — (this is the target) | 1.00 |
| **Pilot** (`suite/v1` dir, `standard`+`capped-thinking`) | knowledge, instruction, tool_calling, **coding** | **agentic (appworld_c)** | **0.50** |
| **Site bundle** (`core-text-v1`, what "pull from site" gives) | knowledge, instruction, tool_calling | **coding (lcb)** AND agentic† | **0.40** |

† `core-text-v1` *declares* agentic membership (`appworld_c`) but only "when localbench is
installed with the appworld extra"; no `appworld_c` itemset ships in the bundle, and the
agentic axis needs the `scoring/agentic_exec/` environment host — not a plain endpoint.

**Consequence for the dogfood plan:** "pull the suite from the site → run → submit → board"
currently yields a **3-axis, 0.40-weight** result (knowledge + instruction + tool_calling).
The pilot we ran adds coding (lcb) but not agentic. The **agentic axis (weight 0.50 — half
the entire index)** is not reachable through either path without the appworld extra + env.

This is exactly the "schema fossilization / suite mismatch" risk the plan flagged, caught
**before** building the submission slice. Good.

## Verified facts (authoritative sources, read 2026-06-29)

### 1. Canonical headline composite — `cli/src/localbench/scoring/axes.py` (single source of truth)
- Agentic (`appworld_c`) **0.50**, Knowledge (`mmlu_pro`) 0.15, Instruction-Following
  (`ifbench`) 0.15, Tool-calling (`tc_json_v1`) 0.10, Coding (`lcb`) 0.10. Sum = 1.0
  (`_validate()` enforces it).
- Math (`olymmath_hard`,`amo`) and Long-Context (`ruler_32k`) are **candidate**, weight 0.0.
- Module docstring: the normal-run Coding axis is the **exec-free `lcb`** proxy;
  `bigcodebench_hard` is the heavier opt-in coding-exec module, *not* pooled into the static
  coding axis "until its execution lane is hardened."

### 2. Site-distributed suite — `web/public/suites/core-text-v1/suite.json`
- `id: core-text-v1`, `version: core-text-v1`, `base_suite_version: suite-v1`,
  `headline_only: true`.
- Ships **3** datasets only: `mmlu_pro` (400), `ifbench` (294), `tc_json_v1` (330).
- `axes` block: knowledge, instruction_following, tool_calling, **agentic = [appworld_c]**.
- Description (verbatim): "Minimal public bundle for local-bench: MMLU-Pro 400, IFBench 294,
  TC-JSON v1 330, plus AppWorld-C agentic membership when localbench is installed with the
  appworld extra. The full repo suite/v1 carries the broader v2.1 modular benchmark set."
- **No `lcb` (coding). No math/long-context.**
- Same file is bundled in CLI package-data (`cli/src/localbench/data/suites/core-text-v1/`)
  and hash-pinned under `release/suites/core-text-v1/<hash>/` (`c1ee1d99…`). `suite_resolver.py`
  `DEFAULT_SUITE_ID = "core-text-v1"`; `normalize_suite_id` maps `v1`/`suite-v1`/`core-text-v1`
  → `core-text-v1`.

### 3. Repo full suite — `suite/v1/suite.json`
- `version: suite-v1`, **10 benches / 7 axes**: amo, olymmath_hard, mmlu_pro, ifbench, bfcl,
  bfcl_multi_turn, lcb, ruler_32k, bigcodebench_hard, tc_json_v1.
- ⚠️ **Membership divergence to reconcile:** this file maps `agentic = [bfcl, bfcl_multi_turn]`,
  but `axes.py` maps `agentic = [appworld_c]`. The file's own note says suite.json "carries axis
  MEMBERSHIP only … A test asserts this membership matches the registry." These do not match for
  the agentic axis — verify whether that test actually covers `suite/v1`, and which definition is
  current. (Did not run the test set to avoid perturbing the live run.)

### 4. The pilot — `runs/campaigns/wave0-gemma-12b-q4xl-cal-20260629/campaign.json`
- `suite_id: core-text-v1`, `suite_dir: …\suite\v1`, `suite_version: suite-v1`,
  `suite_hash: e9db1528e14bf4c128151434324bc4e7ff990542d83a8989eb41662cc8b8e393`.
- `benches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"]`, `tier: standard`,
  `lane: capped-thinking`, `items.total: 1153` (400+294+330+129). `item_set_hashes` only for
  those 4 `.jsonl`.
- So `standard`+`capped-thinking` on a plain endpoint **selects exactly the 4 endpoint-runnable
  axes** and omits agentic (needs appworld env), math (probe-only), long-context, and the
  exec-lane `bigcodebench_hard`.

### Three+ distinct suite hashes observed (must be reconciled / pinned)
- `6b7b80de…` — recorded in memory as "the" suite_hash (provenance now unclear).
- `e9db1528…` — the pilot's effective hash (`suite/v1` dir, 4-bench standard/capped selection).
- `c1ee1d99…` — the released `core-text-v1` bundle hash.
(plus whatever `web/public/suites/core-text-v1/` currently hashes to.)

## Open decisions for the step-3 oracle red-team (do NOT decide unilaterally)

1. **What does a published board row measure?** Full 5-axis headline (needs agentic *and*
   coding both distributed + runnable), or an explicitly-labelled subset/partial composite with
   a visible coverage flag (fits Gate A items 6 & 9 and Gate B "conservative labels")?
2. **Must the site distribute a suite that reproduces the headline?** i.e. add `lcb` (coding)
   to the public bundle and a runnable agentic path (appworld extra + env), so "pull from site"
   genuinely reproduces a board row — or is `core-text-v1` deliberately a headline-*subset*
   public bundle with agentic gated behind an extra and coding omitted?
3. **Which suite_hash is canonical and pinned into each board row?** Reconcile the 3+ hashes;
   define the one a verifier recomputes.
4. **Reconcile the agentic membership divergence** (`suite/v1` bfcl+bfcl_multi_turn vs
   `axes.py` appworld_c) and confirm the membership test's coverage.
5. **Confirm the pilot is calibration-only** (it provably cannot yield a complete headline index
   — missing the 0.50 agentic weight). This is consistent with plan step 1; the first *published*
   row must travel the site path and satisfy whatever (1)–(3) decide.

## What did NOT change
No edits to `suite/v1/suite.json`, `axes.py`, any `core-text-v1` artifact, D1, the submission
API, or any secret. This document is analysis only.

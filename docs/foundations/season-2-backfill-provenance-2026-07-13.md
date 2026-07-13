# Season-2 facet-backfill provenance bundle (2026-07-13)

Machine-verifiable provenance for the five season-2 records published at the index-v4.0 cutover.
All claims below are checkable from this repository, its git history, and the referenced artifacts.

## 1. Item-set precommit (selection could not follow results)

The 50-item `bfcl_multi_turn_base` itemset was committed to this repository at:

- commit `99b3236` — `feat(suite): season-2 v2 suite with split BFCL multi-turn benches (foundation)`
- author date **2026-07-12T12:02:37+10:00** (Brisbane) = 2026-07-12T02:02:37Z
- file `suite/v2/bfcl_multi_turn_base.jsonl` (category-stratified 50/50 split of the frozen 100-item
  `bfcl_multi_turn` set; deterministic SHA-256-ordered selection; exact-union equality with the
  frozen 100 is enforced by `cli/tests/test_v2_bfcl_multi_turn_items.py`).

Every backfill generation run began **after** that commit (all run timestamps below are UTC as
recorded in the run manifests; Brisbane local time is UTC+10):

| Model | run_started_at (UTC) | run_finished_at (UTC) |
|---|---|---|
| gemma-4-12b-it QAT UD-Q4_K_XL | 2026-07-12T19:46:38Z | 2026-07-12T20:36:05Z |
| qwen3-6-27b Q4_K_M | 2026-07-12T20:38:15Z | 2026-07-12T21:29:51Z |
| qwopus3-6-27b-v2-mtp Q4_K_M | 2026-07-12T21:34:33Z | 2026-07-12T22:17:36Z |
| gemma-4-31b-it Q4_K_M | 2026-07-12T22:18:59Z | 2026-07-12T23:01:04Z |
| qwen3-6-35b-a3b UD-Q4_K_M | 2026-07-12T23:02:37Z | 2026-07-12T23:15:14Z |

The composer additionally verifies at composition time that a partial contains EXACTLY the 50
committed item ids (`cli/src/localbench/facet_backfill.py`, `_assert_partial_items`) — wrong,
missing, duplicate, or extra ids are refused fail-closed.

## 2. Complete attempt ledger (no hidden retries)

Every launch of the backfill bench harness on 2026-07-13 (Brisbane), in order. One attempt per
model produced generations; there were **zero** discarded generation runs.

1. `gemma-4-12b-it` — ONE attempt, completed (50/50 items, 0 errors).
2. `qwen3-6-27b` — ONE attempt, completed (50/50, 0 errors).
3. `qwopus3-6-27b-v2-mtp` — ONE failed START (harness exited before any model request: offline
   tokenizer-cache miss for an incorrect `--hf-model-id` operator flag; zero items generated,
   zero tokens sampled), then ONE corrected attempt, completed (50/50, 0 errors). Both the failed
   start and the fix are logged.
4. `gemma-4-31b-it` — ONE attempt, completed (50/50, 0 errors).
5. `qwen3-6-35b-a3b` — ONE attempt, completed (50/50, 0 errors).

Generations are deterministic by pinned policy: temperature 0, top-k 1, seed 1234, single slot,
single client, `gpu-greedy-single-slot-v1`, llama.cpp `b9852 (fd1a05791)`, f16 KV, ctx 32768 — the
identical pins recorded in each parent record; the composer enforces pin equality between parent
and partial before attaching.

## 3. Eligible-record inventory (no favourable selection)

Eligibility rule: every complete bounded-final-v2 season-1 record held by the project (full static
coverage + two-run AppWorld campaign). There are exactly five. ALL five were backfilled and ALL
five are published — none were run and withheld:

- the three publicly ranked rows (gemma-4-12b-it QAT Q4_K_XL, qwen3-6-27b, qwopus3-6-27b-v2-mtp),
- gemma-4-31b-it (public pending ticket …4a182447),
- qwen3-6-35b-a3b (public pending ticket …2b007ff4).

Unranked project-anchor and quant-ladder rows are display-only records by standing policy
(pre-dating season 2) and are not season-2 ranking candidates; they remain labelled season-1
(option-d anchor policy).

## 4. Composed-record manifests

Each published season-2 record embeds a `facet_backfill` block recording: both input paths, the
SHA-256 of the parent record, the partial record, and the partial campaign status file; per-item
campaign attribution for every attached item; both campaigns' timestamps (from the input records —
no wall-clock stamping); and the composed prompt/sampler/budget audit blocks describing BOTH
campaigns. Parents are never mutated; identity strict-equality (model file sha+size, execution
profile id+digest, lane, prompt renderer identity, sampler pins, single-slot evidence) is enforced
fail-closed. Composition then re-runs the suite-coverage gate, the derived-record rescore, and the
season-2 rescore, refusing unless index-v4.0 binds with a complete strict composite.

## 5. Independent re-verification performed before publication

- qwopus coding verdicts re-executed 2026-07-13 in the sandbox verifier under the current harness:
  148/148 items re-run, **0 verdict mismatches**, pass count identical (42) — fresh signed receipt
  `coding-verified.recheck-2026-07-13.json`.
- Rank-stability: item-level bootstrap (two independent seeds, 1000/2000 iters) and a 15-cell
  weight-sensitivity grid (agentic share .50–.70 × tool_use weight .15–.25) produce the identical
  five-model ranking in every cell; adjacent-pair bootstrap probabilities (54–70%) are reflected in
  the published confidence intervals.
- The `call_formatting` (tc_json) facet was demoted to an unweighted diagnostic BEFORE the season
  lock after an external red-team found it contributed no continuous ranking signal (IQR 0.6 across
  the panel); the tc_json conformance gate and coverage requirement are unchanged.

## 6. Artifact identity

All five GGUFs were verified byte-exact against the SHA-256 pinned in their parent records before
any backfill run (two artifacts were re-acquired from public Hugging Face repositories by exact
LFS-sha match; one from a retained local copy; sha verification logs retained). One curated
metadata error found and fixed in the process: the ranked qwen3-6-27b row's `gguf_repo` pointed at
a repository that never hosted the benched artifact; corrected to the verified source.

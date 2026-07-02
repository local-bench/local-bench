# Spec: unify reasoning-leak vocabularies + bench --max-items (2026-07-02)

Implements P0 item 2 of `docs/deploy/plan-ranked-row-2026-07-02.md`. Two work items, both `cli/` only.

## Why (evidence)

The repo has THREE non-identical reasoning-leak vocabularies:
1. `cli/src/localbench/_reasoning.py:6-9` (`strip_reasoning`): `<think>` + harmony
   `<|channel|>analysis/commentary` + `<|message|>`.
2. `cli/src/localbench/lane_conformance.py:38-42` (`has_leaked_reasoning`): think/thought/reasoning
   word-markers, `◁think▷`, `<|think|>`, `<|begin/end_of_thought|>` — **does NOT include the
   channel family (`<|channel>`, `<channel|>`, `<|channel|>`, `<|message|>`)**.
3. Per-lane `reasoning_registry.leak_regexes` in released SCORECARD.json files (gemma4 registry
   already lists `<|channel>` + `<channel|>`).

Consequence (observed on the 2026-07-01 first run AND today's capped-thinking smoke): Gemma-4
channel scaffolding (`<|channel>thought\n<channel|>`, including REPEATED re-opened blocks after a
forced end-of-thinking, and post-budget thinking prose) lands in `message.content`, corrupts the
position-0 scorers (tc_json `raw_decode`, lcb `literal_eval`), and **evades the conformance gate**
— the run stays "headline-comparable" with silently-zeroed axes. A ranked row could be corrupted
the same way. Today's smoke bundle `runs/bench/smoke-leakfix-capped-16k-2026-07-02/` shows the
worst case: item `smoke-ifbench-1` content is a run of repeated `<|channel>thought\n<channel|>`
markers; item `smoke-mmlu-1` content is budget-truncated thinking prose.

## Work item 1 — single leak-marker source of truth

- Create ONE canonical registry of leak markers/regexes (natural home: `_reasoning.py` or a new
  small module) covering at minimum: `<think>`/`</think>`, `◁think▷`, `<|think|>`,
  `<|begin_of_thought|>`/`<|end_of_thought|>`, harmony `<|channel|>analysis`/`commentary`,
  `<|message|>`, and the Gemma channel family `<|channel>` / `<channel|>` (note: single-pipe
  variants, DIFFERENT from harmony's `<|channel|>`), plus the word-marker heuristics currently in
  `has_leaked_reasoning`.
- `lane_conformance.has_leaked_reasoning` and `strip_reasoning` both derive from it. Per-lane
  scorecard `leak_regexes` remain per-lane data but the conformance check must be
  UNION(canonical, per-lane) so a marker missing from a lane registry can't slip through.
- `strip_reasoning` should strip a LEADING `<|channel>thought\n<channel|>` (empty-thought
  scaffold) the way it strips `<think>` blocks — defense-in-depth for endpoint-lane runs through
  servers we don't control. Preserve existing semantics for the markers it already handles
  (including: truncated-unclosed block → empty string).
- Tests: channel-family leaks detected by conformance (unit + a lane_conformance integration
  case); strip_reasoning strips the empty-scaffold prefix; existing strip semantics unchanged.

## Work item 2 — `localbench bench --max-items N`

Add a `--max-items` int flag to the `bench` subcommand (cli.py) that caps items per bench, wired
to the SAME mechanism the quick tier uses in orchestrate.py (~line 1077). Purpose: real-suite
mini-runs through the orchestrated path (e.g. 10-item ifbench/tc_json capped-thinking validation)
without a bespoke suite. Test: flag plumbs through to the orchestrate config and caps items.

## Hard constraints
- `cli/` only. `cli/runs/board/board_v1.json` untouched (git blob `3d058e60…`).
- **Do NOT change `scorecard_identity()` / `registry_digest` / scorer_versions or any released
  SCORECARD.json.** The canonical registry is CODE-side detection; if you find unification
  impossible without touching scorecard identity, STOP and report which piece would.
- Do NOT weaken any existing conformance threshold (≥2% leaked → nonconformant stays).
- Full pytest suite green (baseline 1000 passed / 13 skipped / 1 xfailed). No GPU, no push, no deploy, no commit.

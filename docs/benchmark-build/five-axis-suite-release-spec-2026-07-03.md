# Build spec: 5-axis site-released suite (ranked-row prerequisite)

Date: 2026-07-03. Author: Claude (for Codex implementation, Claude reviews+commits).
Branch: `codex/local-bench-online-backend` (HEAD 4329bad). board_v1 frozen `3d058e60…` — must NOT change.

## Why
The ranked board row is 5-axis: knowledge (mmlu_pro), instruction (ifbench), tool-calling
(tc_json_v1), coding (lcb), **agentic (appworld_c)**. The board's `_ranked` gate
(`scoring/board_scoring.py:434-440`) requires ALL of `headline_web_axes()` measured =
{knowledge, instruction, agentic, tool_calling, coding}. But the only site-released suite today is
`suite-v1-partial-text-code-4axis-v1` (4 axes). A 5-axis bundle that declares a non-released suite
trips `suite.not_site_released` (`submissions/foundation.py:268-269`) → `publishable=false`.
So a publishable 5-axis run needs a site-released 5-axis suite.

Axis weights are FROZEN by board_v1's scorecard (`manifest.scorecard_id a33742c6…`): agentic 0.50,
knowledge 0.15, instruction 0.15, tool 0.10, coding 0.10 (sum 1.00). DO NOT change any weight in
`scoring/axes.py` — that would break the board_v1 freeze. The 5-axis coverage profile inherits
these; its `headline_weight` = 1.00 (all five measured).

## Scope (additive only; no reformatting untouched code; frozen sandbox.py untouched)

### 1. Add a 5-axis CoverageProfile — `cli/src/localbench/suite_release.py`
- Add to `COVERAGE_PROFILES` (currently only `core-text-3axis-v1` @0.40 and
  `partial-text-code-4axis-v1` @0.50, lines 26-39) a new frozen entry:
  ```
  "text-code-agentic-5axis-v1": CoverageProfile(
      profile_id="text-code-agentic-5axis-v1",
      benches=("mmlu_pro", "ifbench", "tc_json_v1", "lcb", "appworld_c"),
      headline_weight=1.00,
      rank_scope="text-code-agentic-5axis-v1",
  )
  ```
  (Confirm the exact bench-id string for appworld_c against `scoring/axes.py:95` = `"appworld_c"`.)

### 2. FIX `coverage_profile_for_benches` 5-set mislabel bug — same file, lines 83-96
- CURRENT BUG: exact-match loop finds no 5-axis profile, then the
  `{"mmlu_pro","ifbench","tc_json_v1","lcb"}.issubset(benches)` branch SWALLOWS a true 5-set
  (which contains that 4-subset) → a 5-axis run mislabels as `partial-text-code-4axis-v1`.
- FIX: add an explicit 5-set check BEFORE the 4-axis issubset branch:
  ```
  if {"mmlu_pro","ifbench","tc_json_v1","lcb","appworld_c"}.issubset(benches):
      return COVERAGE_PROFILES["text-code-agentic-5axis-v1"]
  ```
  Keep exact-match-first behavior intact. Add a regression test: a 5-set returns the 5-axis
  profile (rank_scope text-code-agentic-5axis-v1), a 4-set still returns the 4-axis profile.

### 3. Assemble the 5-axis suite dir + release manifest
- Model on `web/public/suites/suite-v1-partial-text-code-4axis-v1/` (the existing template):
  `suite.json` + the 4 jsonl (ifbench/lcb/mmlu_pro/tc_json_v1) + `itemsets.lock.json` + license
  files. **appworld_c has NO jsonl** (out-of-band, produced by the WSL agentic lane;
  `benchmark_registry.py:23 OUT_OF_BAND_DEFAULT_BENCHES`) — do NOT add an appworld_c file.
- New suite id: `suite-v1-text-code-agentic-5axis-v1`. In its `suite.json`, the `axes` block must
  ADD the agentic axis (`"agentic": ["appworld_c"]`) to the existing 4 (pattern:
  `suite/v1/suite.json:190-193`); the `benches` map stays the 4 http benches. Keep `version`
  `suite-v1`; set `id` to the new suite id.
- Generate the release manifest by calling `build_suite_release_manifest(<suite_dir>,
  coverage_profile_id="text-code-agentic-5axis-v1")`. It pulls axis/bench membership from the
  registry (already 5-axis, incl. agentic→appworld_c), embeds the 5-axis coverage_profile, and
  computes `suite_manifest_sha256`. Record that sha — it feeds step 4.
- Provide a small committed generator (mirror how the 4-axis manifest was produced;
  see `cli/tests/test_suite_release_manifest.py:98-106`) so the manifest is reproducible, and a
  hash-stability test asserting the manifest sha is byte-stable across two builds.

### 4. Register as site-released — `cli/src/localbench/submissions/foundation.py:60-70`
- Add `"suite-v1-text-code-agentic-5axis-v1": "<new sha from step 3>"` to `_SITE_RELEASED_SUITES`.

### 5. Deploy the manifest artifact
- Write the suite dir + `suite_release_manifest.json` under
  `web/public/suites/suite-v1-text-code-agentic-5axis-v1/` so the private site serves it (the
  ranked run will `fetch-suite` it; a local `--suite-dir` does NOT satisfy `_site_released`,
  `foundation.py:277-285`).

## Tests / gates
- New: 5-axis coverage-profile match (step 2), manifest hash-stability (step 3), and a
  `validate-submission-bundle`-level test that a synthetic 5-axis bundle declaring the new suite is
  `publishable:true` with zero blocking reasons (mirror the existing 4-axis publishable test).
- Full `uv run pytest` green. Do NOT touch board_v1; assert `git hash-object
  cli/runs/board/board_v1.json` == `3d058e6074bd781cc488c03255904b5f9599e37e` unchanged.
- Do NOT commit — leave the tree dirty for Claude review + commit.

## Out of scope (Claude/other tracks)
Agentic verdict host-derivation, robustness fixes, the actual GPU runs. This spec only makes a
5-axis run *publishable*; measuring the agentic axis is the shakeout + ranked run.

# Task 1 report: profile-owned budgets

## Implementation

- Added the frozen `ExecutionProfileBudget` tuple to reasoning profile entries and minted `generic_think_tags_32768_v1` with the brief's exact static, serving, agentic, cache, context-policy, and timeout values.
- Auto generic-thinking resolution now selects the 32k profile. `generic_think_tags_8192_v1` remains explicitly selectable and retains the pre-0.4.14 two-pass behavior.
- `ResolvedExecutionContract` carries the selected runtime budget. `BoundedFinalProfileRuntime` derives the forcing values from that resolved contract; the request runner therefore sends 32768 then 16384 for the new profile.
- The forced-result record carries `static_max_generated_tokens=49152` into the unchanged audit input, so `budget_audit.max_promised_total` is profile-owned rather than shadowed by suite-item `max_tokens`.
- Manifest caps read the resolved contract for the new profile. The signed agentic `orchestrate.py` is byte-identical to the T0 baseline; no contract ceremony was run or modified.
- The new profile is scorecard-lookup addressable without being added to the signed legacy `REASONING_REGISTRY` catalog. Existing profile payloads/digests and agentic-contract coverage remain frozen.

## Red/green evidence

- RED: `tests/test_profile_owned_budgets.py -q` initially failed with `generic_think_tags_8192_v1 != generic_think_tags_32768_v1` when auto resolution still selected the legacy profile.
- GREEN: the first profile-resolution regression passed after adding the new profile and generic runtime selection.
- RED mutation proof: temporarily changing the new entry's static think cap to 8192 made the release regression fail with `current_trace == [8192, 16384]`, instead of `[32768, 16384]`.
- GREEN after restoring 32768: `tests/test_profile_owned_budgets.py -q` passed 3/3.

## Verification

- Focused related tests: 98 passed in 23.37s.
- Signed-contract check plus focused profile regressions: 5 passed in 1.00s.
- Updated integration/revision focused set: 11 passed in 3.59s.
- Full CLI: `.venv/Scripts/python.exe -m pytest tests -q` -> 2160 passed, 17 skipped, 4 xfailed, 21 warnings in 396.01s.
- Full web: `npm test` -> 113 passed / 1 skipped test files; 692 passed / 1 skipped tests in 285.27s.
- `git diff --check` passed. `git diff --exit-code -- cli/src/localbench/orchestrate.py` passed.

## Files

T1 changes are confined to CLI profile resolution, execution-contract plumbing, request forcing/runner/manifest seams, and direct CLI tests. No suite item, itemset, run, release, agentic-loop, public-schema, or web source artifact changed.

## Self-review and concerns

- The 32k profile intentionally remains outside the signed legacy agentic catalog. It is separately lookup-addressable so scorecard resolution works, while the signed v8 contract stays valid. T2/T3 must decide how to serialize and publicly expose the full tuple and semantic digest; this task intentionally does neither.
- The legacy 8192 control is locked to the exact two request bodies and 8192/8192 caps under a 16384 item cap. The release regression also hashes the suite and selected itemset before and after the 32k/legacy paths, proving byte stability.

## Fix round 1: contract source and 32k conformance repair

### Implementation

- Removed the copied static budget fields from `ForcingFormat`. A bounded-final runtime now carries a reference to its resolved execution contract, and `_requests` forwards that contract uniformly into request shaping.
- `bounded_final_forcing` consumes only `execution_contract.budget`; it no longer has either a profile-ID condition or a forcing-format budget fallback. `manifest._caps` likewise reads any resolved contract budget without profile-ID gating.
- The new `generic_think_tags_32768_v1` entry now owns conformance metadata that agrees with its tuple: 32768 think, 16384 final, and the additive `32768 + 16384` total. The frozen 8192 entry and its metadata were not changed.

### Red/green evidence

- RED: `.venv/Scripts/python.exe -m pytest tests/test_profile_owned_budgets.py -q` produced `2 failed, 3 passed in 0.77s`.
  - The arbitrary resolved-contract test observed `[32768, 16384]` instead of `[123, 456]`, proving the profile-ID gate.
  - The 32k conformance test observed `think_cap == 8192` instead of `32768`.
- GREEN: the same command passed `5 passed in 0.65s` after the minimal refactor and corrected entry metadata.
- Green refactor: split the new contract-source coverage into `test_profile_owned_budget_contract.py` to keep both test modules under 250 non-comment LOC. Exact focused command:
  `.venv/Scripts/python.exe -m pytest tests/test_profile_owned_budgets.py tests/test_profile_owned_budget_contract.py tests/test_bounded_final_profiles.py tests/test_budget_forcing.py tests/test_execution_contract.py tests/test_execution_contract_serving.py tests/test_execution_contract_release_gate.py -q`
  -> `69 passed in 1.49s`.

### Final verification

- CLI: `.venv/Scripts/python.exe -m pytest tests -q` -> `2162 passed, 17 skipped, 4 xfailed, 23 warnings in 399.44s`.
- Web: `npm test` -> `113 passed / 1 skipped test files; 692 passed / 1 skipped tests in 283.86s`.
- `git diff --check` passed; `git diff --exit-code -- cli/src/localbench/orchestrate.py` passed.

### Deferred minor

- As directed, the release regression’s current-byte pre/post suite-hash comparison remains deferred for final-review triage; this repair does not expand that scope.

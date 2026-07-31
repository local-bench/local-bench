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

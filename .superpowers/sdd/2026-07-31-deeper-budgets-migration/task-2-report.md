# Task 2 report — contract tuple and semantic digest

## Status

Implemented and verified on top of `7fa07b6` and `8f9410a` without changing any signed v8-covered source bytes or performing contract signing/ceremony work.

## Implementation

- Added canonical serialization for the complete 13-field `ExecutionProfileBudget` tuple in `execution_profile_semantics.py`.
- Added `ResolvedExecutionContract.semantic_sha256`, calculated as SHA-256 over UTF-8 JSON with sorted keys, compact separators, and the full tuple only.
- The minted `generic_think_tags_32768_v1` tuple serializes to:

  `{"agentic_context_tokens":32768,"agentic_max_generated_tokens_per_task":65536,"agentic_max_output_tokens_per_turn":1024,"agentic_max_turns":40,"context_extension_policy":"none","context_fit_policy":"exact-or-fail","kv_cache_k_dtype":"f16","kv_cache_v_dtype":"f16","per_task_timeout_s":3000,"server_context_tokens":65536,"static_final_tokens":16384,"static_max_generated_tokens":49152,"static_think_tokens":32768}`

  Its semantic digest is `e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058`.
- Threaded the same flat tuple and `semantic_sha256` into:
  - the full internal execution-contract record used by campaign manifests and serving resume identity;
  - the public execution-profile record used by the persisted run manifest;
  - `structured_execution_profile`, which preserves the additive fields when present while continuing to parse the frozen legacy v1 fields.
- Preserved no-budget legacy/direct contract serialization as the old shape. This is required by the frozen 0.4.13 item-bounded 8192 compatibility fixture; production resolver-created contracts carry the T1-owned budget and therefore carry semantic identity.
- Reused the existing serving resume chain instead of adding another budget owner: `execution_contract_record` feeds the normalized serving resume identity, which feeds `AgenticResumeSeed`, the LoopConfig-derived sampling identity, and the persisted task-journal header.
- Added an observable agentic resume regression: a journal created with `agentic_max_turns=40` is resumed with an otherwise identical tuple at `39`; `run_with_reruns` raises `ResumeIdentityMismatchError` at journal open and the model factory records zero requests/constructions.
- Did not derive or change LoopConfig budget values (T4), add public schema-v2 validation (T3), change registry payload/digest logic, or touch signed host/worker modules.

## RED/GREEN evidence

### Initial RED

Command:

`.venv/Scripts/python.exe -m pytest tests/test_execution_contract_semantic_identity.py -q`

Result: collection failed with `ImportError: cannot import name 'execution_profile_semantic_payload'`, proving the semantic contract API was absent.

### Signed-wall design correction

The first implementation attempt added a semantic field directly to `task_journal_types.py` and `serving/agentic_resume.py`. The focused run produced `2 passed, 1 failed`; the failure was the real v8 drift wall:

- expected covered-behavior digest: `15c1cd8c52fae87e2aec9e4757e22cd113d3a5827b52040f78d2177992b08c36`
- observed covered-behavior digest: `ca5b6f9a910cd3508c68d6004d9a07079dcbf3d997dca7a2de2de676f9e41c9c`
- differing component: `host_agent_loop_scorer_source_sha256`

Inspection showed the v8 C6 source bundle explicitly covers both files. Those edits were removed completely. The final implementation reuses the existing `normalized_server_identity` field, which already derives from `execution_contract_record`, so no signed bytes changed.

### Focused GREEN

- Semantic tests alone after the signed-safe redesign: `3 passed in 0.96s`.
- Broader contract/serving/agentic identity set: `69 passed in 8.42s`.
- Final fresh focused gate:

  `.venv/Scripts/python.exe -m pytest tests/test_execution_contract_semantic_identity.py tests/test_execution_contract_release_gate.py tests/test_execution_contract.py tests/test_execution_contract_serving.py tests/test_generic_gguf_renderer_integration.py tests/test_bounded_final_profiles.py::test_bounded_final_generic_two_pass_uses_actual_reasoning_tokens_for_budget_audit -q`

  Result: `24 passed in 3.11s`.

### Full-gate correction

The first full CLI run produced `1 failed, 2164 passed, 17 skipped, 4 xfailed, 23 warnings in 398.60s`. The only failure was the frozen legacy no-budget fixture. Adding the registry tuple to that fixture changed the request from the expected 1024 cap to 8192, proving it would violate legacy behavior. The implementation was corrected so semantic fields are additive only for contracts with a resolved T1 budget, and the fixture was restored unchanged.

## Final verification

- CLI, from `cli/`:

  `.venv/Scripts/python.exe -m pytest tests -q`

  `2165 passed, 17 skipped, 4 xfailed, 21 warnings in 399.81s`.
- Web, run serially afterward from `web/`:

  `npm test`

  `113 passed / 1 skipped test files; 692 passed / 1 skipped tests in 283.15s`.
- Signed v8 drift wall: included in the fresh focused gate above; all `3` release-gate tests passed.
- Strict Python no-excuse audit over changed/new semantic modules and new test: `no violations in 3 file(s)`.
- LSP diagnostics: no errors in all changed/new Python files.
- `git diff --check`: passed.
- Tracked generated artifacts: none added or modified by the test runs.
- `ruff` module was unavailable in the CLI virtualenv; the installed Ruff LSP and the required no-excuse audit were clean.

## Files

- `cli/src/localbench/execution_profile_semantics.py`
- `cli/src/localbench/execution_contract.py`
- `cli/tests/test_execution_contract_semantic_identity.py`
- `cli/tests/test_execution_contract.py`
- `cli/tests/test_execution_contract_serving.py`
- `.superpowers/sdd/2026-07-31-deeper-budgets-migration/task-2-report.md`

## Self-review

- The semantic payload contains exactly the 13 T1-owned tuple fields and no template, model, probe, or registry metadata.
- Expected digests in tests are literal, independently computed values rather than recomputations through production helpers.
- A 40-to-39 mutation changes both `semantic_sha256` and the normalized serving/agentic resume identity.
- Resume refusal is proven through the real `run_with_reruns` → journal-open boundary before model construction, not by checking a helper constant.
- Legacy execution-profile catalog serialization/digests, `KNOWN_EXECUTION_PROFILES`, `SUPERSEDES`, formula strings, and reason codes were not edited.
- No signed v8-covered source file differs from HEAD.
- No T3 schema-v2 validation or T4 LoopConfig derivation was pulled forward.

## Concerns

- `ResolvedExecutionContract.budget` remains optional because frozen legacy/direct fixtures and archived shapes exist. `semantic_sha256` is therefore defined only for fully resolved contracts; serializers omit additive semantic fields for a no-budget legacy contract. All production resolver-created ranked contracts carry the T1-owned tuple.
- Public schema-v2 enforcement remains intentionally deferred to T3. T2 emits and preserves the fields but does not require them at the validation boundary.

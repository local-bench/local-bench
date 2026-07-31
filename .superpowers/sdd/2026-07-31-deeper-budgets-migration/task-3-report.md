# Task 3 report — public execution-profile schema v2

## Outcome

- Preserved legacy v1 public records byte-shape unchanged: the existing nine structured fields remain valid without `schema_version`.
- Added `localbench.execution_profile.v2` for `generic_think_tags_32768_v1`, carrying the complete 13-field budget/serving tuple and T2-owned `semantic_sha256`.
- Added fail-closed Python public-record parsing for missing, malformed, or tuple-inconsistent 32768-v2 records using `ExecutionProfileBudget` and `semantic_sha256_for_budget` as the tuple/digest owners.
- Updated the accepted-result JSON Schema and site Zod contract as additive v1/v2 unions; the site structured type is discriminated by absent v1 versus explicit v2 `schema_version`.
- Left `KNOWN_EXECUTION_PROFILES`, `SUPERSEDES`, the reasoning registry, and suite bytes untouched.

## TDD evidence

| Scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Python legacy parse plus incomplete/inconsistent 32768-v2 rejection, before implementation | `cli/.venv/Scripts/python.exe -m pytest tests/test_public_execution_profile_schema.py -q` | RED: 4 failed, 1 passed for missing version and non-rejected v2 mutations | `.omo/evidence/task-3-public-schema/red-cli.txt` |
| Python required base-field rejection | same focused pytest invocation | RED: 1 failed, 5 passed because missing `selection_policy_id` was dropped instead of rejected | `.omo/evidence/task-3-public-schema/red-cli-required-base.txt` |
| Python frozen-ID negative control | same focused pytest invocation | RED: 1 failed, 6 passed because a mutated and rehashed tuple reused the 32768 ID | `.omo/evidence/task-3-public-schema/red-cli-rehashed-tuple.txt` |
| Site v2 parsing before implementation | `npm test -- tests/execution-profile-contract.test.ts` | RED: 1 failed, 2 passed; v2 keys rejected as unknown | `.omo/evidence/task-3-public-schema/red-web.txt` |
| Site ID-only negative control | same focused Vitest invocation | RED: 1 failed, 2 passed because an ID-only 32768 record bypassed v2 | `.omo/evidence/task-3-public-schema/red-web-id-only-v2.txt` |
| Python final focused contract | `cli/.venv/Scripts/python.exe -m pytest tests/test_public_execution_profile_schema.py tests/submissions/test_projection_runtime_contract.py -q` | GREEN: 17 passed | `.omo/evidence/task-3-public-schema/green-cli-focused-final.txt` |
| Site focused contract | `npm test -- tests/execution-profile-contract.test.ts` | GREEN: 3 passed | `.omo/evidence/task-3-public-schema/green-web-focused.txt` |

## Validation evidence

| Success criterion | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Python execution-contract/submission regression | `cli/.venv/Scripts/python.exe -m pytest tests/test_execution_contract.py tests/test_execution_contract_semantic_identity.py tests/test_generic_gguf_renderer_integration.py tests/submissions/test_execution_profile_submission.py tests/submissions/test_projection_runtime_contract.py tests/test_public_execution_profile_schema.py -q` | 34 passed | `.omo/evidence/task-3-public-schema/cli-contract-regression.txt` |
| Site public-boundary regression | `npm test -- tests/execution-profile-contract.test.ts tests/community-live-board-schema-consistency.test.ts` | 2 files passed, 11 tests passed | `.omo/evidence/task-3-public-schema/web-contract-regression.txt` |
| Python changed-file lint | `ruff check src/localbench/execution_profile_semantics.py src/localbench/execution_contract.py tests/test_public_execution_profile_schema.py tests/submissions/test_projection_runtime_contract.py` | exit 0, all checks passed | `.omo/evidence/task-3-public-schema/ruff-focused.txt` |
| TypeScript compiler | `npm run typecheck` | exit 0, `tsc --noEmit` | `.omo/evidence/task-3-public-schema/web-typecheck.txt` |
| Required full CLI gate | `cli/.venv/Scripts/python.exe -m pytest tests -q` | 2,172 passed, 17 skipped, 4 expected xfails, 0 failed | `.omo/evidence/task-3-public-schema/full-cli-pytest.txt` |
| Required full web gate, run after CLI | `npm test` | 114 files passed, 1 file skipped; 695 tests passed, 1 skipped; 0 failed | `.omo/evidence/task-3-public-schema/full-web-npm-test.txt` |

LSP evidence: Ruff reported no diagnostics for both changed Python modules. The configured TypeScript/Deno LSP refresh timed out, so the successful project `tsc --noEmit` invocation above is the authoritative TypeScript diagnostic artifact.

No tracked generated artifacts were created by either full gate. Existing unrelated untracked workspace content was preserved.

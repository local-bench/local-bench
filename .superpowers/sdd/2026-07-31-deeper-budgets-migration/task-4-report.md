# Task 4 report — agentic LoopConfig from resolved contract

## Outcome

- The actual agentic campaign activation boundary now derives `max_turns`, per-turn output, cumulative task output, context window, and per-task timeout from one resolved execution-profile budget. The 32768 profile reaches the worker as exactly `40 / 1024 / 65536 / 32768 / 3000`.
- Resolved v1 budgets also use their own complete tuple. Genuine no-budget legacy activation keeps the historical 3072 scored override and has no invented cumulative bound.
- The loop caps each request to the task's remaining generated-token budget. Hitting the cumulative bound preserves `cap_exceeded` and adds only `cap_dimension: "task_output_tokens"`.
- Task/report diagnostics now serialize turn-output p95/p99/max, history-window truncation rate (history drops / total turns), and cumulative-task-output-cap-hit rate (hits / total tasks). Empty input yields null extrema and zero rates; legacy journal rows default the additive raw fields safely.
- Resume sampling and persisted loop configuration include the new cumulative bound and timeout. C6 attempt/rerun decisions are unchanged; resumed and uninterrupted campaigns remain identical. No C8 matrix, suite, signed-contract, `KNOWN_EXECUTION_PROFILES`, or `SUPERSEDES` artifact was changed.
- The owner override was honored: no ceremony, signature, contract JSON, drift-wall assertion, skip, or xfail was changed.

## TDD evidence

| Scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Missing resolved wiring, cumulative cap, history count, and aggregate diagnostics | `uv run pytest -q` on the five new boundary/unit nodes | RED: 5 failed for `24 != 40`, missing LoopConfig cumulative field, missing history field, and missing aggregate fields | `.omo/evidence/t4-agentic-loop/red.txt` |
| Actual campaign activation plus cumulative loop and diagnostic contracts | `uv run pytest -q tests/test_wave3_attestation_run_id.py tests/test_appworld_protocol_c_units.py tests/test_agentic_task_journal_integration.py` | GREEN: 61 passed | `.omo/evidence/t4-agentic-loop/green-focused-final.txt` |
| Cumulative hard bound | focused Protocol-C unit in the preceding invocation | request caps observed as `[5, 2]`; terminal outcome `cap_exceeded`; `cap_dimension == "task_output_tokens"`; second block not executed | `.omo/evidence/t4-agentic-loop/green-focused-final.txt` |
| 32768 resolved tuple at worker activation | real orchestration boundary test in the preceding invocation | captured `LoopConfig` equals `40 / 1024 / 65536 / 32768 / 3000` | `.omo/evidence/t4-agentic-loop/green-focused-final.txt` |

## Validation evidence

| Success criterion | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Agentic/profile regression | focused eight-file pytest regression | 114 passed | `.omo/evidence/t4-agentic-loop/agentic-regression-final-2.txt` |
| Signed-wall isolation for ordinary CLI behavior tests | focused CLI/orchestrate/SGLang/vLLM pytest invocation | 23 passed | `.omo/evidence/t4-agentic-loop/drift-isolation.txt` |
| Final CLI isolation fixture file | `uv run pytest -q tests/test_cli_bench_exit_codes.py` | 20 passed | `.omo/evidence/t4-agentic-loop/cli-isolation-final.txt` |
| Python lint | `uv run ruff check` on all changed Python files | exit 0, all checks passed | `.omo/evidence/t4-agentic-loop/ruff-final-v2.txt` |
| Python syntax/import compilation | `uv run python -m compileall -q` on changed production surfaces | exit 0 | `.omo/evidence/t4-agentic-loop/compileall-final-v2.txt` |
| LSP diagnostics | Ruff LSP directory diagnostics on agentic package | 50 files scanned, 0 files with errors, 0 diagnostics | `.omo/evidence/t4-agentic-loop/lsp-final.txt` |
| Covered-behavior budget projection | direct `_extract_covered_behavior` assertion | `40 / 1024 / 65536 / 32768 / 3000` | `.omo/evidence/t4-agentic-loop/covered-budget-projection.txt` |
| Patch hygiene | `git diff --check` | exit 0 | `.omo/evidence/t4-agentic-loop/diff-check-final-v2.txt` |
| Required full CLI gate | `uv run pytest -q` | 2,176 passed, 17 skipped, 4 expected xfails, 21 warnings, exactly 1 expected signed-v8 red | `.omo/evidence/t4-agentic-loop/full-cli-final-v2.txt` |
| Required full web gate, run serially after CLI | `npm test` | 114 files passed, 1 skipped; 696 tests passed, 1 skipped; exit 0 | `.omo/evidence/t4-agentic-loop/full-web-final-v2.txt` |

## Expected signed-v8 red

- Node ID: `tests/test_execution_contract_release_gate.py::test_live_covered_behavior_matches_baked_signed_contract`
- Message: `ExecutionContractDriftError: agentic execution contract drift: expected 15c1cd8c52fae87e2aec9e4757e22cd113d3a5827b52040f78d2177992b08c36, observed bd7512d085f561fd29f45643fccf2b5deaa0fb7c5a1b9f502dc3b15e82ae6ae5`
- Classification: intentional signed-v8 covered-behavior drift caused by T4 source/behavior changes. This is the sole full-CLI failure.

`basedpyright` is not installed in the project environment; the attempted invocation is captured in `.omo/evidence/t4-agentic-loop/basedpyright.txt`. Ruff lint, Ruff LSP diagnostics, compileall, focused tests, and both required full gates provide the available strict diagnostics.

No tracked generated artifact was produced by validation. Unrelated tracked/untracked workspace content was preserved.

# Task 5 report — behavioral/capacity probe split

## Outcome

- The template/reasoning behavioral probe now owns the named local bound `BEHAVIORAL_PROBE_MAX_TOKENS = 16`. Request capture proves the deep profile never leaks its 32768 think cap, 49152 total-generation allowance, or 65536 server context into the probe completion.
- The separately named capacity probe queries the live `/props`, `/v1/models`, and `/slots` surfaces, writes `runtime-capacity-probe.json`, returns accepted evidence, and fails closed on unavailable, malformed, missing, ambiguous, or contradictory facts.
- The 32768 profile now exact-fails before launch unless `--ctx 65536` is supplied. Its live capacity gate requires effective/model/slot context exactly 65536, `n_ctx_train >= 65536`, f16/f16 cache, fit reported off, one 65536 slot, and a reported flash-attention state. Launch argv remains pinned to b10076-supported `--cache-type-k`, `--cache-type-v`, `--fit off`, and `--flash-attn`; argv is not accepted as runtime proof.
- Existing 8192 profiles, formulas, reason codes, registry identities, `KNOWN_EXECUTION_PROFILES`, `SUPERSEDES`, suite bytes, signed contracts, and release-wall behavior were not changed.

## TDD and behavioral evidence

| Scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Capacity behavior absent | `uv run pytest tests/test_runtime_capacity_probe.py tests/test_runtime_probe.py -q` | RED at collection: `ModuleNotFoundError: localbench.runtime_capacity_probe` | `.omo/evidence/t5/red-runtime-probes.txt` |
| Deep-profile server capacity not enforced | focused two-node serving test | RED at collection: missing `ProfileServerContextMismatchError` | `.omo/evidence/t5/red-profile-server-context.txt` |
| b10076-style top-level effective props not consumed | `uv run pytest tests/test_runtime_capacity_probe.py -q` | RED: positive fixture rejected with cache/fit/flash reported `None` | `.omo/evidence/t5/red-b10076-props-shape.txt` |
| Legacy profile accidentally gated | focused legacy serving node | RED: legacy 8192 contract rejected at its previously accepted non-deep server context | `.omo/evidence/t5/red-legacy-profile-scope.txt` |
| Positive capacity evidence | final focused four-file pytest invocation | Accepted evidence contains 65536 effective/model context, 262144 `n_ctx_train`, f16/f16, fit off, flash on, one 65536 slot, and is byte-equivalent to the persisted JSON | `.omo/evidence/t5/focused-final.txt` |
| Fail-closed capacity matrix | same invocation | Below/scaled context, missing/low native context, K/V cache drift, fit on/auto/unreported, missing/multi/undersized slots, malformed props, and missing flash state all raise and persist `passed: false` | `.omo/evidence/t5/focused-final.txt` |
| Behavioral probe bound | same invocation | Captured completion request is exactly `[16]` for `generic_think_tags_32768_v1` | `.omo/evidence/t5/focused-final.txt` |
| Public CLI integration | same invocation | Hermetic HTTP server accepts canonical 65536 launch, live capacity probe, behavioral probe, and 32768/16384 forced completion flow | `.omo/evidence/t5/focused-final.txt` |
| Final focused regression | `uv run pytest -q tests/test_runtime_capacity_probe.py tests/test_runtime_probe.py tests/test_serving_bench.py tests/test_generic_gguf_renderer_integration.py` | 63 passed | `.omo/evidence/t5/focused-final-v2.txt` |

## Validation evidence

| Success criterion | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Required full CLI gate | `uv run pytest -q` | 2,195 passed, 17 skipped, 4 expected xfails, 23 warnings, exactly one expected signed-v8 red | `.omo/evidence/t5/full-cli-final-v2.txt` |
| Required full web gate, run serially after CLI | `npm test` | 114 files passed, 1 skipped; 696 tests passed, 1 skipped; exit 0 | `.omo/evidence/t5/full-web-final-v2.txt` |
| Python LSP diagnostics | error diagnostics on all nine changed Python files | 9/9 returned no diagnostics | `.omo/evidence/t5/lsp-errors.txt` |
| New-module type check | `uv run --with basedpyright basedpyright src/localbench/runtime_capacity_probe.py` | 0 errors; two warnings at the established HTTP JSON/exception seams | `.omo/evidence/t5/basedpyright-capacity.txt` |
| New-module lint | `uv run --with ruff ruff check src/localbench/runtime_capacity_probe.py` | all checks passed | `.omo/evidence/t5/ruff-new-module.txt` |
| Python compilation | `uv run python -m compileall -q` on the four changed production modules | exit 0 | `.omo/evidence/t5/compileall.txt` |
| Patch hygiene | `git diff --check` | exit 0 | `.omo/evidence/t5/diff-check.txt` |

## Expected signed-v8 red

- Node ID: `tests/test_execution_contract_release_gate.py::test_live_covered_behavior_matches_baked_signed_contract`
- Message: `ExecutionContractDriftError: agentic execution contract drift: expected 15c1cd8c52fae87e2aec9e4757e22cd113d3a5827b52040f78d2177992b08c36, observed 5eb2b45961377cc2d3942f08e66910ae9de4edc51c44c6ac3854f05aa4a7f75e`
- Classification: the unchanged, intentional signed-v8 wall. No ceremony, signature, contract JSON, skip, xfail, or wall assertion was modified.

## Live-runtime limitation

No live b10076 llama-server was available in this workspace, so the real-GPU capacity scenario could not be executed. The pinned upstream b10076 source confirms `/props` reports effective context and slot count, `/v1/models` reports `n_ctx`/`n_ctx_train`, and `/slots` reports per-slot context, but stock `/props` does not report effective cache type, fit state, or flash-attention state. The new gate therefore intentionally rejects stock/ambiguous evidence until the deployed runtime exposes those effective properties; launch argv never substitutes for them. The positive end-to-end test uses a real local HTTP server implementing the required endpoint evidence.

No tracked generated artifact was produced by validation. Unrelated tracked/untracked workspace content was preserved.

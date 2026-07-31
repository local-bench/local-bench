# Task 5 report — behavioral/capacity probe split

## Outcome

- The template/reasoning behavioral probe now owns the named local bound `BEHAVIORAL_PROBE_MAX_TOKENS = 16`. Request capture proves the deep profile never leaks its 32768 think cap, 49152 total-generation allowance, or 65536 server context into the probe completion.
- The separately named capacity probe combines stock b10076 `/props`, `/v1/models`, and `/slots` responses with the current managed process epoch in `serve.log`, writes `runtime-capacity-probe.json`, returns accepted evidence, and fails closed on unavailable, malformed, missing, ambiguous, stale, or contradictory facts.
- The 32768 profile now exact-fails before launch unless `--ctx 65536` is supplied. `/props` is authoritative for effective context and slot count, `/slots` corroborates per-slot allocation, `/v1/models` supplies `n_ctx`/`n_ctx_train`, and b10076 startup lines supply effective `n_ctx`, `n_ctx_seq`, `n_seq_max`, K/V cache types, and flash-attention state. The CLI `on`/`off` values are matched to b10076's logged `enabled`/`disabled` vocabulary. Canonical `--fit off` is required but never sufficient: acceptance also requires exact live endpoint/log agreement and no `common_params_fit` evidence.
- Existing 8192 profiles, formulas, reason codes, registry identities, `KNOWN_EXECUTION_PROFILES`, `SUPERSEDES`, suite bytes, signed contracts, and release-wall behavior were not changed.

## TDD and behavioral evidence

| Scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Capacity behavior absent | `uv run pytest tests/test_runtime_capacity_probe.py tests/test_runtime_probe.py -q` | RED at collection: `ModuleNotFoundError: localbench.runtime_capacity_probe` | `.omo/evidence/t5/red-runtime-probes.txt` |
| Deep-profile server capacity not enforced | focused two-node serving test | RED at collection: missing `ProfileServerContextMismatchError` | `.omo/evidence/t5/red-profile-server-context.txt` |
| Stock b10076 composite attestation absent | `uv run pytest -q tests/test_runtime_capacity_probe.py` | RED: 20 failures because the verifier had no managed startup-log/argv interface | `.omo/evidence/t5-fix-round-1-red.txt` |
| Current launch epoch binding absent | focused four-node epoch invocation | RED: all 4 cases reject the missing byte-boundary/PID interface | `.omo/evidence/t5-fix-round-2-red.txt` |
| Public CLI append isolation absent | public CLI renderer integration node | RED: stale 32768 and current 65536 startup records are mixed, returning exit 70 | `.omo/evidence/t5-fix-round-2-e2e-red.txt` |
| Legacy profile accidentally gated | focused legacy serving node | RED: legacy 8192 contract rejected at its previously accepted non-deep server context | `.omo/evidence/t5/red-legacy-profile-scope.txt` |
| Positive stock-runtime capacity evidence | final focused four-file pytest invocation | Stock endpoint payloads plus realistic b10076 log lines attest 65536 endpoint/log/slot context, 262144 `n_ctx_train`, f16/f16, fit off, flash on, and one slot; persisted JSON includes the startup-log SHA-256 | `.omo/evidence/t5-fix-round-1/refactor-verification.txt` |
| Fail-closed composite matrix | same invocation | Missing/malformed/mismatched logs, context/slot/parallel drift, K/V or flash drift, fit activity, argv-only claims, noncanonical fit argv, endpoint mismatch, and missing/multi/undersized slots all raise and persist `passed: false` | `.omo/evidence/t5-fix-round-1/refactor-verification.txt` |
| Behavioral probe bound | same invocation | Captured completion request is exactly `[16]` for `generic_think_tags_32768_v1` | `.omo/evidence/t5/focused-final.txt` |
| Public CLI integration | same invocation | Hermetic stock-shaped HTTP responses plus managed b10076 startup log accept the canonical 65536 launch, behavioral probe, and 32768/16384 forced completion flow | `.omo/evidence/t5-fix-round-1/refactor-verification.txt` |
| Current-epoch fail-closed matrix | expanded focused invocation | stale-valid/current-missing, stale-invalid/current-valid, partial mixed epochs, resume append, invalid byte ranges, and invalid PIDs behave as specified | `.omo/evidence/t5-fix-round-2-focused-static-utf8.txt` |
| Final focused regression | expanded six-file pytest invocation | 81 passed | `.omo/evidence/t5-fix-round-2-focused-static-utf8.txt` |

## Validation evidence

| Success criterion | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Required full CLI gate | `uv run pytest -q` | 2,207 passed, 17 skipped, 4 expected xfails, 23 warnings, exactly one expected signed-v8 red | `.omo/evidence/t5-fix-round-2-full-cli-utf8.txt` |
| Required full web gate, run serially after CLI | `npm test` | 114 files passed, 1 skipped; 696 tests passed, 1 skipped; exit 0 | `.omo/evidence/t5-fix-round-2-full-web-utf8.txt` |
| Python LSP diagnostics | all nine fix-round Python paths, severity all | 9/9 returned no diagnostics | `.omo/evidence/t5-fix-round-2-lsp-diagnostics.txt` |
| Verifier type check | `uv run --with basedpyright basedpyright --level error` on the changed capacity/process modules | 0 errors, 0 warnings, exit 0 | `.omo/evidence/t5-fix-round-2-focused-static-utf8.txt` |
| Verifier lint | `uv run --with ruff ruff check` on the capacity verifier and epoch test/support modules | all checks passed, exit 0 | `.omo/evidence/t5-fix-round-2-focused-static-utf8.txt` |
| Python compilation | `uv run python -m compileall -q` on the three changed production modules | exit 0 | `.omo/evidence/t5-fix-round-2-focused-static-utf8.txt` |

## Expected signed-v8 red

- Node ID: `tests/test_execution_contract_release_gate.py::test_live_covered_behavior_matches_baked_signed_contract`
- Message: `ExecutionContractDriftError: agentic execution contract drift: expected 15c1cd8c52fae87e2aec9e4757e22cd113d3a5827b52040f78d2177992b08c36, observed 5eb2b45961377cc2d3942f08e66910ae9de4edc51c44c6ac3854f05aa4a7f75e`
- Classification: the unchanged, intentional signed-v8 wall. No ceremony, signature, contract JSON, skip, xfail, or wall assertion was modified.

## Live-runtime evidence design and limitation

No live b10076 llama-server binary was available in this workspace, so the real-GPU scenario could not be executed. Pinned upstream b10076 source was inspected directly: `tools/server/server-context.cpp` defines stock `/props` context/slot fields and `/v1/models` metadata; `src/llama-context.cpp` emits effective `n_ctx`, `n_ctx_seq`, `n_seq_max`, and `flash_attn`; `src/llama-kv-cache.cpp` emits actual K/V types. Stock `/props` does not emit cache, fit, or flash fields, so all fabricated custom fields were removed from positive fixtures.

The supported path is now achievable with stock b10076. Immediately before each managed child is spawned, the append-mode log byte offset is captured on `LaunchedServer`; the capacity probe reads and UTF-8 decodes only that child's suffix. The persisted evidence records the child PID, inclusive start/exclusive end byte range, and SHA-256 of the exact suffix. Stale records cannot supply or contaminate current fields, including on reused `--out` or `--resume` directories; invalid identity/range data fails closed.

Cache and flash acceptance requires current-process startup-log observations, not argv. Fit acceptance is composite because `--fit off` suppresses the fit routine rather than emitting a positive runtime field: the canonical argv pin must be present, `/props`, `/slots`, and current startup contexts must agree exactly at 65536 with one slot, and any current-epoch `common_params_fit` line fails closed. Argv alone cannot satisfy the gate.

No tracked generated artifact was produced by validation. Unrelated tracked/untracked workspace content was preserved.

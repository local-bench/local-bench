# Task 6 report — Profile-derived timeouts and renewable keepawake

## Outcome

T6 now derives transport, no-progress, campaign, and keepawake bounds from the resolved execution budget at the supported 10 tokens/second floor. Resolved-profile HTTP calls use split connect/read/write/pool timeouts, static two-pass calls use each pass's actual maximum, and agentic turns use a profile-derived read bound capped by the existing task deadline. Genuine legacy/no-budget construction retains its prior timeout fallback.

The supervisor now uses a finite renewable keepawake lease. It acquires the lease for a profile-derived horizon, renews it on observable completed-item progress, resets the no-progress clock on progress, and releases it on completion, error, cancellation, or watchdog termination. Renewal failure aborts closed.

## Authoritative formulas

All named constants live in `localbench.timeout_budgets`:

- Minimum generation throughput: `10 tokens/second`.
- Generation allowance: `ceil(max_output_tokens / 10)`.
- Request read timeout: `generation allowance + 30s read/finalize reserve`.
- Split transport bounds: `connect=10s`, `write=30s`, `pool=10s`.
- Static item maximum: `3 * (think read + final read) + 60s item-finalize reserve`.
- No-progress allowance: `max(static item maximum, profile per-task timeout)`.
- Keepawake lease: `no-progress allowance + 60s teardown reserve`.
- Remaining work: `remaining static items * static item maximum + remaining agentic tasks * profile per-task timeout * 3 campaign runs`.
- Campaign bound: `300s startup + max(remaining work, no-progress allowance) + 300s finalization`.

This is remaining-work-derived; there is no fixed approximately-24-hour campaign constant.

## Exact deep-profile examples

- 32,768-token think request: `ceil(32768 / 10) = 3277s` generation, `3307s` read.
- 16,384-token final request: `ceil(16384 / 10) = 1639s` generation, `1669s` read.
- One static item: `3 * (3307 + 1669) + 60 = 14988s`.
- No-progress allowance: `max(14988, 3000) = 14988s`.
- Renewable keepawake lease: `14988 + 60 = 15048s`.
- One remaining static-item campaign: `300 + 14988 + 300 = 15588s`.
- One 1,024-token agentic turn: `ceil(1024 / 10) + 30 = 133s`, still bounded by the profile-owned 3,000s task deadline.
- Two remaining agentic tasks: `300 + (2 * 3000 * 3) + 300 = 18600s`.
- Ninety-six remaining agentic tasks: `300 + (96 * 3000 * 3) + 300 = 864600s`; the duration grows from remaining work rather than a hidden daily cap.

Persisted timeout evidence carries provenance `profile-derived-10-tokens-per-second` plus the named reserves, attempt/run factors, no-progress horizon, lease horizon, and campaign horizon.

## Verification

- Focused timeout and supervisor scenarios: `uv run pytest tests/test_timeout_budgets.py tests/test_supervisor.py -q` — **9 passed**. This covers the real HTTP timeout extension, actual two-pass maxima, legacy fallback, agentic turn bound, fake-clock no-early-kill/just-after kill, progress reset/renewal, fail-closed renewal, and release paths. Artifact: `.omo/evidence/t6-timeout-leases/focused-final.txt`.
- Full CLI: `uv run pytest -q` — **1 failed, 2214 passed, 17 skipped, 4 xfailed**. The sole failure is the required signed-v8 wall, `tests/test_execution_contract_release_gate.py::test_live_covered_behavior_matches_baked_signed_contract`; it was not modified or weakened. Artifact: `.omo/evidence/t6-timeout-leases/full-cli-final-attempts.txt`.
- Full web, run serially after CLI: `npm test` — **114 files passed, 1 skipped; 696 tests passed, 1 skipped**. A first post-change run encountered a one-off Miniflare `EADDRINUSE` proxy collision and the required complete rerun passed. Artifacts: `.omo/evidence/t6-timeout-leases/full-web-final.txt` and `.omo/evidence/t6-timeout-leases/full-web-final-rerun.txt`.
- Static verification: Ruff reported `All checks passed!`; basedpyright reported `0 errors, 0 warnings, 0 notes` for the two new typed modules; compileall reported `compileall_ok=True`; `git diff --check` reported clean. Artifacts: `.omo/evidence/t6-timeout-leases/ruff-final.txt`, `basedpyright-final.txt`, `compileall-final.txt`, and `git-diff-check-final.txt`.

No contract ceremony, suite bytes, UI transition, docs/version/changelog, publish, or push was performed.

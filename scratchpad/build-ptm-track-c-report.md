# Track C build report

Date: 2026-07-18
Branch: `ptm/track-c`
Push performed: no

## Commits made

- `41df810 feat(auto-validator): add publish moderation daemon`
- `df2eca6 docs(auto-validator): add maintainer runbook`
- `667843a fix(auto-validator): print dry-run verification payload`
- `docs(track-c): record daemon build results` (this report's commit)

## Files changed

- `scripts/auto_validator.py` - scheduled-task entrypoint, argument parsing, PID lifecycle, polling, and public test surface.
- `scripts/auto_validator_core.py` - FIFO initial-decision flow, catch-all terminal rejection, dry-run output, intents/outcomes, signed decision logging, reconciliation, alerts, and work retention.
- `scripts/auto_validator_http.py` - stdlib list/status/download client and installed `post_admin_verification` adapter that replaces the released helper's admin header with the validator-only wire header.
- `scripts/auto_validator_model.py` - typed configuration, protocols, reason mapping, secret/path scrubbing, backoff, guard, and payload construction.
- `scripts/auto_validator_state.py` - rotating log, PID lock, and write-ahead intent journal.
- `scripts/auto_validator_coding.py` - explicit post-Bonsai coding pass, digest-pin/key gates, projection refresh, fresh revision/hash reads, single 409 retry, and parking alert.
- `scripts/auto_validator_README.md` - maintainer prerequisites, scheduled-task command, recovery, guards, dry-run, and coding-pass runbook.
- `cli/tests/test_auto_validator.py` - 27 network/Docker-free tests covering the base workorder and all binding red-team amendments.
- `scratchpad/build-ptm-track-c-report.md` - this report.

No file under `cli/src/` was modified. The user-provided untracked workorder was read but not staged or changed.

## Test and verification results

Required targeted command:

```text
uv run --project cli pytest cli/tests/test_auto_validator.py -q
27 passed in 0.84s
PASS
```

Required full command:

```text
uv run --project cli pytest -q
1910 passed, 24 skipped, 4 xfailed, 24 warnings in 419.85s (0:06:59)
PASS
```

The first full-suite run used the automatically selected CPython 3.13.11 venv and reported `17 failed, 1893 passed, 24 skipped, 4 xfailed`. Runtime evidence identified only missing test prerequisites: the RC gate requires CPython 3.14.2, BFCL tests require the pinned `ShishirPatil/gorilla@6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` checkout, Gemma rendering requires the declared HF extra, and the compatibility gate requires pip plus the web lockfile dependencies. The ignored local environment was rebuilt/synced accordingly; no tracked dependency or source file changed.

After the dry-run print correction, the exact targeted command remained green. A later full-suite attempt was stopped after host contention from an already-running `localbench`/`llama-server` benchmark caused a compatibility failure and prolonged CPU-bound execution, consistent with the owner rule that these workloads run sequentially. The affected compatibility file was then verified independently:

```text
uv run --project cli pytest cli/tests/test_b2a_client_compat_manifest.py -q
5 passed in 81.79s
PASS
```

Additional checks:

```text
uv run --project cli python <programming-skill>/check-no-excuse-rules.py scripts/auto_validator.py scripts/auto_validator_model.py scripts/auto_validator_state.py scripts/auto_validator_http.py scripts/auto_validator_core.py scripts/auto_validator_coding.py
no violations in 6 file(s)
PASS

uv run --project cli python -m py_compile scripts/auto_validator.py scripts/auto_validator_model.py scripts/auto_validator_state.py scripts/auto_validator_http.py scripts/auto_validator_core.py scripts/auto_validator_coding.py
exit 0
PASS
```

Manual QA:

- Actual CLI with the live host benchmark processes present: exit 0, `guard: bench-active` written, no stderr, PID lock released.
- Real daemon components against a local HTTP server with an injected idle process listing: exact request `/api/admin/submissions?status=pending_verification&limit=50`, validator header present, admin header absent, cycle `ok`, startup reconciliation true, PID lock released.

## Deviations and justification

1. The workorder names `scripts/auto_validator.py` as the new script. Its implementation is split into five focused support modules so every production module remains below the 250-nonblank-line quality ceiling; `auto_validator.py` remains the only operator entrypoint and the path-imported test surface.
2. Released v0.4.2 `post_admin_verification` accepts `SiteCredentials.admin_secret` and cannot directly emit the binding validator header. The daemon still calls that exact installed public helper and supplies a transport adapter that removes `x-localbench-admin-secret` and sends only `x-localbench-validator-secret`. This satisfies both the mandated API reuse and R3 wire contract without modifying `cli/src/`.
3. Fresh idempotency/revision reads use the public submission-status route without a privileged header. Section 12.11 permits the validator credential only on list, bundle download, and verification POST, so sending it on the status read would violate the binding credential scope.
4. The ignored test environment was synced to its documented prerequisites to obtain the required full-suite result. No environment artifact was committed.

## Incomplete

Nothing incomplete. All base behavior and R1-R5 amendments are implemented, documented, tested, and committed locally. No push was performed.

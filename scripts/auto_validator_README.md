# Auto-validator daemon

`auto_validator.py` processes publish-then-moderate submissions in strict FIFO
order using the released `local-bench-ai==0.4.2` verifier. It is a maintainer-box
script, not part of the packaged CLI.

## Prerequisites

- Use the Python executable from the v0.4.2 released-CLI environment.
- Keep the suite release directory available locally.
- Put `VALIDATOR_API_SECRET` in a UTF-8 text file readable only by the scheduled
  task identity. The secret is read from that file; it is never accepted on the
  command line or written to the daemon log.
- Track A must expose validator-authenticated list, bundle-download, and
  verification routes.

## Scheduled task

Run continuously at the default 120-second interval:

```powershell
C:\Users\Michael\lb-user-runs\venv-042-pypi\Scripts\python.exe scripts\auto_validator.py --site https://local-bench.ai --validator-secret-file C:\Users\Michael\.localbench\local-bench-validator-secret.txt --interval 120
```

Suite resolution: with no `--suite-dir`, each submission's suite is resolved from the
local registered-bundle cache (`~/.cache/localbench/suites/<suite_release_id>/<hash>/`,
populated by `localbench fetch-suite`; override the root with `--suite-cache-root`).
A submission whose suite bundle is not cached (or is ambiguous) is SKIPPED with a log
line — never rejected — and stays pending until the bundle is fetched. Passing
`--suite-dir` forces one directory for every submission (single-suite operation and
the coding pass, which requires it).

```text
```

For a one-cycle smoke check, add `--once`. For a verification-only rehearsal,
add `--once --dry-run`; the daemon downloads and verifies each still-pending
bundle but does not POST, journal an intent, or append a decision-log entry.

The default state directory is
`%USERPROFILE%\.localbench\auto-validator`. `--work-dir` overrides only the
active work directory.

## Runtime behavior

Each cycle checks the pause/process guard, lists up to 50 pending submissions,
sorts them oldest-first, rechecks each current status, downloads the raw bundle,
and calls `localbench.submissions.status_update.verify_submission`. The initial
POST carries `operation: initial_decision`. A verifier exception is converted
to a bounded, projection-free terminal rejection so a malformed FIFO head
cannot block later submissions.

Before every POST, the daemon appends an intent to `intents.jsonl`. It appends
the HTTP outcome before the signed local decision log. Startup reconciliation
checks any unmatched intent against current server state and writes a
`reconciled_auto_verify` decision entry for a terminal state.

Completed work entries move to `done`; locally rejected entries move to
`failed`. Each destination retains its newest 20 entries. A failed POST leaves
the active work entry and pending server row available for the next cycle.

## Guards, retry, and operator signals

The cycle is skipped with `guard: bench-active` when `pause` exists or the
Windows process list shows `llama-server` or a LocalBench benchmark process.
The PID lock at `lock.pid` prevents concurrent daemon instances; a dead PID is
replaced with a warning.

Consecutive API failures back off from 30 seconds to a 10-minute cap. The fifth
failure writes `ALERT.txt` and exits so the scheduled task can restart it. The
UTF-8 line-buffered `auto-validator.log` rotates at 5 MB and retains three
rotations. Resolve the underlying fault and remove `ALERT.txt` after review.

An accepted response with `published=false` is successful: the server-side
freeze alarm deliberately blocked publication. The daemon records the result
and continues; it does not poll a digest or alarm endpoint.

## Separate coding pass

Run coding only after Bonsai/GPU work has stopped. The command hard-refuses to
start when the guard is active. The image must be digest-pinned and the receipt
signing key stays in a file path, never in argv as secret material:

```powershell
C:\Users\Michael\lb-user-runs\venv-042-pypi\Scripts\python.exe scripts\auto_validator.py --site https://local-bench.ai --suite-dir C:\Users\Michael\lb-user-runs\suite\v1 --validator-secret-file C:\Users\Michael\lb-user-runs\secrets\validator-api-secret.txt --coding-pass --coding-image bigcodebench/bigcodebench-evaluate@sha256:REPLACE_WITH_APPROVED_DIGEST --receipt-signing-key C:\Users\Michael\lb-user-runs\secrets\coding-receipt.pem
```

The pass selects accepted, published projections whose coding axis is
`not_measured`, runs `localbench code --pending-run`, verifies again with the
signed coding record, and POSTs `operation: projection_refresh` using a freshly
read state revision and prior projection digest. A 409 causes one fresh-read
retry. A second conflict parks the row and writes `ALERT.txt`.

## Tests

```powershell
uv run --project cli pytest cli/tests/test_auto_validator.py -q
uv run --project cli pytest -q
```

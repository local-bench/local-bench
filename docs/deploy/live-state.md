# Live deployment state

Generated: 2026-06-29
Expected mode: Private
Expires for decision-making: 24h
Source: scripts/launch-smoke.ps1 -ExpectedMode Private -WriteState

This file is the canonical live-facts document for launch-prep decisions. Handoffs and runbooks should link here instead of duplicating endpoint expectations.

## Expected public behavior

Unauthenticated production traffic is expected to be closed by private mode:

- `https://local-bench.ai/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.pages.dev/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/api/suites/core-text-v1/manifest`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.

HTTP 200 from any unauthenticated production host or deployment alias is a release-blocking public leak.

## Hosts and suite

- Apex host: `local-bench.ai`
- WWW host: `www.local-bench.ai`
- Pages host: `local-bench.pages.dev`
- Suite id: `core-text-v1`
- Suite hash: `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`
- Expected suite file count: `11`

## Deployment facts

- Live production deployment id: `049f238e`
- Commit: `05263f1`
- Branch: `main`
- Prior gated deployment id: `5a325e77`

## Leak-closure note

Two pre-gate production deployments, `494f03cd` and `ccedf382`, previously served unauthenticated HTTP 200 and were deleted on 2026-06-29. Deployment aliases remain part of the smoke gate because any deployment built before private-mode middleware, or any new deployment missing preview/production private vars, can re-open the leak.

## Current blockers

The online submission/admin surfaces remain intentionally blocked while these production secrets are missing:

- `ADMIN_API_SECRET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

Smoke checks for ticket, upload, and admin paths should report WARN while these secrets are absent, not FAIL.

## Private bypass

Owner bypass token path:

```text
C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt
```

The token must not be committed, echoed, logged, or included in command transcripts. `scripts/launch-smoke.ps1 -BypassTokenPath <path>` reads it at runtime and redacts it from output.

## Refresh command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1 -ExpectedMode Private -WriteState
```

That command writes `docs/deploy/live-state.generated.json` for machine-readable observations. This markdown file remains the human canonical live-facts document.

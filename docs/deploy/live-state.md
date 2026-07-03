# Live deployment state

Generated: 2026-07-03
Expected mode: Private
Expires for decision-making: 24h
Source: scripts/launch-smoke.ps1 -ExpectedMode Private -WriteState (plus out-of-band submission-leg verification, 2026-07-03)

This file is the canonical live-facts document for launch-prep decisions. Handoffs and runbooks should link here instead of duplicating endpoint expectations.

## Expected public behavior

Unauthenticated production traffic is expected to be closed by private mode:

- `https://local-bench.ai/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.pages.dev/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/api/suites/core-text-v1/manifest`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.

HTTP 200 from any unauthenticated production host or deployment alias is a release-blocking public leak.

All four private signatures plus both alias-domain checks PASSED on 2026-07-03 after the redeploy.

## Hosts and suite

- Apex host: `local-bench.ai`
- WWW host: `www.local-bench.ai`
- Pages host: `local-bench.pages.dev`
- Suite id (manifest smoke): `core-text-v1`
- Suite hash: `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`
- Expected suite file count: `11`
- Site-released submission suite: `suite-v1-partial-text-code-4axis-v1` (manifest sha `b3fc4019...`) — the only suite the ticket route binds.

## Deployment facts

- Commit: `40423f4` (branch `main` on the deploy remote, pushed 2026-07-03)
- Deployment id: unverified — wrangler is unauthenticated on this machine (`npx wrangler login` pending with Michael); the smoke's alias-leak checks still cover the known historical ids.
- Health payload now reports `storage.queue: false` BY DESIGN: the dead `VERIFICATION_QUEUE` producer binding was removed (Pages cannot consume queues). d1 and r2 must be `true`.

## Leak-closure note

Two pre-gate production deployments, `494f03cd` and `ccedf382`, previously served unauthenticated HTTP 200 and were deleted on 2026-06-29. Deployment aliases remain part of the smoke gate because any deployment built before private-mode middleware, or any new deployment missing preview/production private vars, can re-open the leak.

## Secrets and submission pipeline state (verified 2026-07-03)

`ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` are SET and proven working: admin-gated ticket issuance (401 without the admin secret, 201 with), R2 presigned PUT of an 18.6MB bundle, and owner-bypass health/manifest all succeeded out-of-band. The smoke script does not probe these paths (state-mutating) and emits one informational WARN instead.

Current real blockers:

1. `POST /api/submissions/{ticket}/complete` returns 400 `invalid_result_bundle` for orchestrated runs: the CLI writer emits removed `result_bundle_v1` top-level fields (`trust_tier`, `serving_verification_level`, `output_path`). Writer-compliance fix in flight on branch `retry-errored-resume`; the site contract is correct and unchanged.
2. `npx wrangler login` (Michael) — needed for deployment-id enumeration, remote D1 `0003` apply, and log tailing. Not needed for submissions themselves.

The legacy finalize Bug 2 (opaque 500) is retired: the deployed structured error handling returns precise coded errors.

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

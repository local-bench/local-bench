# Live deployment state

Generated: 2026-07-04
Expected mode: Private
Expires for decision-making: 24h
Source: scripts/launch-smoke.ps1 -ExpectedMode Private -WriteState (plus authenticated wrangler deployment/D1 sweep after the contract-v2 deploy, 2026-07-04)

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
- Expected suite file count: `15` (contract v2 added the 4 LICENSES entries that were missing from the catalog file list; suite dir hash unchanged — this was the `fetch-suite --site` fix)
- Site-released submission suites (contract v2): registered pairs `suite-v1-text-code-agentic-5axis-v1` (manifest sha `5a47282a...`, the ticket default) and `suite-v1-partial-text-code-4axis-v1` (manifest sha `b3fc4019...`). Community tickets must name a registered pair explicitly.

## Deployment facts

- Commit: `8742223` (Wave 5 board + provenance rendering, consistency fix, freeze re-pin eabdb69d…; branch `main` on the deploy remote, pushed 2026-07-05 early). Current production deployment id `992deab1-a6a0-43a5-b8d1-873267a77529` (source `8742223`). Smoke after this deploy: 24 PASS / 0 FAIL (private mode). Prior pin: `f0d7b5a2` (source `a0e4d20`).
- Pending rows added by live QA 2026-07-05: `ticket_2d2f80a8640d4dc48fb8052744ec1ea2` (community, display name "QA Fixture", hidden, pending) — content-equivalent to the ranked run; recommend REJECT after owner eyeball (its purpose, proving the live community leg, is served).
- Deployment id: VERIFIED 2026-07-04 via authenticated wrangler (account `michael.russell@clarityconsultive.com`, id `4af6606afb8636c5243c521f9bb26c70`). All enumerated production Pages deployment aliases return HTTP 503 or 404 — no leak on any live deployment.
- Health payload now reports `storage.queue: false` BY DESIGN: the dead `VERIFICATION_QUEUE` producer binding was removed (Pages cannot consume queues). d1 and r2 must be `true`.

## Leak-closure note

Two pre-gate production deployments, `494f03cd` and `ccedf382`, previously served unauthenticated HTTP 200 and were deleted on 2026-06-29. Deployment aliases remain part of the smoke gate because any deployment built before private-mode middleware, or any new deployment missing preview/production private vars, can re-open the leak. Full-fleet alias sweep 2026-07-03 (all 8 live deployments) returned 503 across the board.

## Secrets and submission pipeline state (verified 2026-07-03)

`ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` are SET and proven working: admin-gated ticket issuance (401 without the admin secret, 201 with), R2 presigned PUT of an 18.6MB bundle, and owner-bypass health/manifest all succeeded out-of-band. The smoke script does not probe these paths (state-mutating) and emits one informational WARN instead.

Both prior blockers are CLEARED as of 2026-07-03:

1. RESOLVED — `POST /api/submissions/{ticket}/complete`: the CLI writer-compliance fix landed on `main` (commit `e1876eb`) and was proven end-to-end. A full orchestrated submission (canary bundle sha `e8b34c05`) went ticket → R2 PUT → `/complete` → admin-verify → admin-decision `hidden`, all accepted; the 400 no longer reproduces. The banned `result_bundle_v1` top-level fields are stripped, and the embedded `manifest.integrity.publishable` now matches the validator (the W3 normalize-after-apply ordering fix). The site contract was correct and unchanged throughout.
2. RESOLVED — `npx wrangler login` completed; deployment enumeration and remote D1 `0003` apply are done (see below). Log tailing (`wrangler tail`) is now available.

Remote D1 state (2026-07-04): migration `0004_submission_contract_v2.sql` applied to `localbench_prod` (data-preserving submissions rebuild: server-derived `origin` column with CHECK, `expires_at`, `run_payload_sha256`, `duplicate_of`, unique indexes, `rate_counters` table). Pre-migration backup taken to `C:\Users\Michael\.localbench\backups\d1-localbench_prod-2026-07-04-pre0004.sql` and verified to contain both accepted rows. Post-migration query confirmed all 5 rows intact with `origin=project_anchor`; both accepted submissions (`ticket_790a73b6…` ranked row, `ticket_4cfd0aa2…` canary) remain `accepted` + publish `hidden`. Earlier state (2026-07-03): migration `0003_submission_reconcile.sql` applied.

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

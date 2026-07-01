# Submit-CLI rewrite spec (2026-07-01)

## Why
The web submission backend was reconciled to the 3 contracts (foundation/2a/2b), but the CLI
submission client (`cli/src/localbench/submissions/client.py` + the `submit` / `fetch-suite`
commands in `cli/src/localbench/cli.py`) still speaks the OLD backend protocol and does not work
against the live routes, and never learned the private-gate bypass. This rewrite makes the CLI
drive the REAL end-to-end path so an external user (and Michael as submission #0/#1) can: pull the
suite from the site -> run locally -> submit the result bundle -> poll status, all through the live
(currently private-gated) site.

## Authoritative sources (READ for exact shapes; do NOT change these files)
- New routes/handlers: `web/functions/_lib/submission-api.ts`, `web/functions/_lib/submission-contracts.ts`,
  `web/functions/api/submissions/*`, `web/functions/api/admin/submissions/*`.
- Private gate: `web/functions/_middleware.ts` (bypass = `x-localbench-bypass` header, `?lb_bypass=` query,
  or `lb_private_bypass` cookie; secret `LOCALBENCH_PRIVATE_BYPASS_TOKEN`).
- Python-authoritative verifier: `validate-submission-bundle` + `rescore-bundle`
  (`cli/src/localbench/submissions/foundation.py`, `projection.py`).

## The new flow the CLI must implement
1. **fetch-suite** — GET the suite manifest + files from the site, hash-verify. MUST send the bypass header.
2. **submit** (happy path):
   a. `raw_bundle_sha256` = sha256 of the result_bundle_v1 JSON file (the run output).
   b. **ticket**: POST `/api/submissions/tickets` body
      `{accepted_suite_terms:true, bundle_sha256:<raw_bundle_sha256>, submitter_id:<id> | public_key:<hex>, declared_model_slug?}`
      -> `submission_envelope_v1` (`ticket_id`, `expected_suite_release_id`, `expected_suite_manifest_sha256`,
      `max_upload_bytes`, `expiry`, ...). project_anchor tickets are admin-gated -> also send `x-localbench-admin-secret`.
   c. **request-upload**: POST `/api/submissions/request-upload` body `{ticket_id, raw_bundle_sha256}`
      -> `{upload_url, r2_key, bucket, content_sha256, expires_seconds, method:"PUT"}`.
   d. **PUT** the result_bundle_v1 JSON bytes to `upload_url` (content-addressed by raw_bundle_sha256).
   e. **complete**: POST `/api/submissions/{ticket_id}/complete` body `{raw_bundle_sha256, size_bytes}`
      -> `{submission_id, status:"pending_verification", ...}`.
3. **status** — GET `/api/submissions/{ticket_id}` -> the submission row.
4. **admin-verify** (maintainer, Python-authoritative):
   a. Identify the target submission (accept an explicit `--submission-id` + local bundle path; use an admin
      list route only if one exists in the new backend — check web/functions/api/admin/submissions).
   b. Run `validate-submission-bundle` + `rescore-bundle` locally on the bundle -> produce the
      `accepted_result_projection_v1` + a `localbench.submission_status_update.v1`
      (`{schema_version, status:"accepted"|"rejected", accepted, blocking_reasons, projection_path,
      projection_sha256, raw_bundle_sha256, reason, validated_at, validator_version, validator_commit?}`).
   c. Upload the projection to R2 if the design requires, then POST
      `/api/admin/submissions/{submission_id}/verification` with the status_update (admin + bypass headers).
5. **admin-decision** (publish): POST `/api/admin/submissions/{submission_id}/decision`
   `{publish_state:"hidden"|"preview"|"published"}` (admin + bypass).

## Bypass + admin secret (headers on every site call)
- Bypass: send `x-localbench-bypass: <token>` when available, from (in order) `--bypass-token-file`,
  `--bypass-token`, or env `LOCALBENCH_PRIVATE_BYPASS_TOKEN`. Owner file:
  `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt`. If no token, omit (public mode).
- Admin secret: admin-gated calls send `x-localbench-admin-secret` from `--admin-secret-env`
  (default `LOCALBENCH_ADMIN_SECRET`) or `--admin-secret-file`. Owner file:
  `C:\Users\Michael\.localbench\local-bench-admin-secret.txt`.

## Bundle format
The uploaded object is the **result_bundle_v1 JSON** (a post-fcf9a9f run's localbench-run.json). NOT a zip.
The complete route reads it from R2 and validates result_bundle_v1. Old-schema bundles (e.g. the calibration
pilot) are OUT OF SCOPE for the CLI; Claude normalizes those separately for the #0 canary.

## Out of scope / do not
Old zip/.lbsub format + old ticket shape (remove/replace). Ed25519 keygen/signing may remain as the
`submitter_id`-vs-`public_key` choice but is NOT required by the new tickets route. Do NOT change any
`web/` route (they are the contract), `cli/runs/board/board_v1.json`, or any secret. No deploy, no push.

## Tests
Unit tests with httpx `MockTransport` for the full happy path (ticket -> request-upload -> PUT -> complete
-> status) + admin-verify (status_update POST) + the disabled(503)/unauthorized(401)/gate paths. Assert the
bypass header is present on every site call when a token is configured. Keep full `uv run --project cli pytest`
green.

## Guardrails
Branch codex/local-bench-online-backend; board_v1.json byte-identical (print git hash-object, expect 3d058e60...);
NO secrets, NO deploy, NO git commit/push; leave ALL changes uncommitted for review; smallest correct change.

## Acceptance / evidence
- `localbench submit` works end-to-end against a mock backend (unit tests green).
- Every site call sends the bypass header when a token is configured; admin calls send the admin header.
- Concise report: files changed, the new flow wiring, exact test commands + pass counts, git hash-object of
  board_v1.json, and what is ready to drive the live #0/#1 next.

# Spec: submission-pipeline fixes — Bug 2, migrations, split-brain routes (2026-07-02)

Implements P2 of `docs/deploy/plan-ranked-row-2026-07-02.md`. **web/ only. LOCAL work only:
no deploys, no remote wrangler commands (auth is currently expired), no pushes, no commits.**
Findings below were code-verified during the 2026-07-02 comprehensive review.

## Background (verified findings)

- **Split-brain backend:** two incompatible implementations bound to the same D1 `submissions`
  table. NEW: `functions/_lib/submission-api.ts` + `submission-store.ts` (migration **0002**
  schema). LEGACY: `functions/_lib/api.ts` (migration **0001** schema). Route wiring today:
  ticket/request-upload/complete/verify/decision → NEW; **`GET /api/submissions/{id}`
  (`[submissionId].ts:7` → `api.ts:166`) and `GET /api/admin/submissions` (`submissions.ts:4` →
  `api.ts:174`) → LEGACY** — they select 0001 columns (`r2_key, bundle_sha256,
  manifest_payload_sha256, size_bytes`, `api.ts:288-290`, `:183-188`) that don't exist in 0002 →
  **broken on the live DB** (`localbench submit status` is dead in prod).
- **Migrations:** `0001` creates the old `submissions`; `0002` uses `create table if not exists`
  with a completely different column set → on a FRESH DB 0002 is a no-op over 0001's table and
  its `create index … on submissions(publish_state)` (`0002:82`) fails. Remote was fixed by a
  manual `DROP TABLE submissions` + re-apply (canary doc); **fresh-DB rebuild is still broken.**
- **Bug 2 (finalize 500):** `POST /api/submissions/{id}/complete` 500s with a SyntaxError shape
  ONLY when the bundle-sha matches. Local Miniflare with clean 0002 passes the identical path
  end-to-end (`tests/submission-routes.test.ts:138-177`) → the failure is remote-D1-specific.
  Leading hypothesis: remote schema/CHECK drift after the manual reconcile (e.g. a missing/
  mistyped column among `uploaded_at, status, raw_bundle_size_bytes, bundle_schema_version,
  suite_release_id, suite_manifest_sha256, tier` written by `markPendingVerification`,
  `submission-store.ts:41-55`) surfacing as a mis-parsed error inside the D1 client. The staged
  defensive catch (committed `c5426a8`) currently **swallows the error with no logging**.
- **Suite mismatch:** `handleFinalizeSubmission` never checks the uploaded bundle's
  `manifest.suite.suite_release_id`/`suite_manifest_sha256` against the ticket's
  `expected_suite_release_id`/`expected_suite_manifest_sha256`. Also the suites catalog
  (`functions/_lib/suite-catalog.ts`) serves ONLY `core-text-v1` while
  `submission-contracts.ts:61-62` defaults expectations to `suite-v1-partial-text-code-4axis-v1`
  (`DEFAULT_SUITE_MANIFEST_SHA256 = b3fc4019…`).

## Work items

1. **Structured logging in the finalize catch** (`submission-api.ts:113-118`): `console.error`
   with error name/message/stack + a short breadcrumb (route, submission_id, which leg) — NEVER
   the bundle body, headers, or any secret. Same for a new catch-log in
   `handleApplyVerificationUpdate` if it has an equivalent swallow path.
2. **Local repro matrix** (vitest + Miniflare D1; this is TEST code, not prod):
   (a) fresh DB with 0002 only → finalize 200 (exists, keep green);
   (b) **fresh DB applying 0001 THEN 0002 in sequence** → assert the migration conflict is real
   (0002 no-ops, index creation fails) — this test should FAIL against the current migration set
   and PASS once 0003 lands (write it to target the post-0003 behavior; document the pre-0003
   failure in a comment);
   (c) a drifted-schema case: apply a 0002-minus-one-column variant (e.g. drop `tier`) and run
   the exact `markPendingVerification` UPDATE → assert the handler now returns the structured 500
   AND logs (proves the logging + gives the Bug-2 signature a local reproduction).
3. **0003 migration** (`web/migrations/0003_*.sql`): idempotent reconcile — drop-first recreate
   of the 0002-shape `submissions` (+ its indexes) and `board_entries` if absent; drop the dead
   0001 tables (`verification_jobs`, `admin_decisions`, and `suites` if nothing references it —
   grep first; `/api/suites` uses the static catalog, not D1). After 0003, a from-scratch
   `migrations apply` (0001→0002→0003) must produce exactly the schema the NEW code needs.
   D1 is index-only state (R2 is truth), so dropping pointer tables is acceptable — say so in a
   header comment.
4. **Rewire the split-brain routes** to the 0002 store: `GET /api/submissions/{id}` returns the
   NEW `publicSubmission` shape; `GET /api/admin/submissions` lists from the 0002 table (admin-
   gated, ordered by created/updated appropriately). Retire the dead LEGACY submission handlers
   in `api.ts` (keep `handleSuites`/`handleSuiteManifest`/`handleHealth`); delete the dead queue
   producer path (`verification_jobs` / `VERIFICATION_QUEUE .send()`) or leave clearly
   dead-marked if removal ripples into wrangler.jsonc bindings — prefer removal + drop the
   producer binding from `wrangler.jsonc` (Pages can't consume queues anyway, per the go-live
   oracle).
5. **Suite-match enforcement at finalize**: when the ticket row carries expected suite fields,
   reject with 409 (`code: "suite_mismatch"`) if the validated bundle's
   `manifest.suite.suite_release_id` or `.suite_manifest_sha256` differ. Tests: mismatch → 409;
   match → 200; ticket without expectations → unchanged behavior.
6. **Serve the 4-axis release in the catalog**: add `suite-v1-partial-text-code-4axis-v1` to
   `suite-catalog.ts` (files + sha256 + size from
   `web/public/suites/suite-v1-partial-text-code-4axis-v1/SHA256SUMS` and the release manifest —
   include `suite_release_manifest.json` itself in the served file list; compute sizes from the
   actual files on disk) and extend `suiteById`. Test: `/api/suites/{id}/manifest` serves it.

## Hard constraints
- `web/` only (functions, migrations, tests, lib, wrangler.jsonc if item 4 requires). Do NOT
  touch `web/public/data/**` (frozen board anchors), `web/public/suites/**` content,
  `web/functions/_middleware.ts` (private gate), or anything under `cli/`.
- No deploy, no push, no remote wrangler, no commit. Local vitest/typecheck only.
- All web vitest green (baseline ~99 tests incl. the finalize regression pair); `npm run
  typecheck` (or `tsc --noEmit` per package scripts) clean; do not weaken existing tests.
- Keep responses/state transitions contract-compatible with `cli/src/localbench/submissions/client.py`
  (the 3-contract flow committed at `1220a6c`) — the CLI is the consumer; if a response shape
  must change, STOP and report instead.

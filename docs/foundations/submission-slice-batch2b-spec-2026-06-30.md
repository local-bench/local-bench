# Submission slice — BATCH 2b spec (2026-06-30)

Implements oracle build-order steps 7–9 on top of 2a (commit 2326e30) and the foundation
(440f540). Mostly **reconcile + wire + render** — the intake routes already exist under
`web/functions/api/`. All offline-testable; NO secrets, NO deploy, site stays private-gated.

Design source of truth: `docs/foundations/submission-slice-design-decided-2026-06-30.md`
(3 contracts + Python-authoritative verification + partial-row publishing). 2a artifacts to
build on: contracts `result_bundle_v1` / `submission_envelope_v1` / `accepted_result_projection_v1`;
suite release `suite-v1-partial-text-code-4axis-v1` (manifest sha256 `b3fc4019…`); D1 migration
`web/migrations/0002_submission_slice_index.sql` (tables `submissions` + `board_entries`);
projection→board-row mapper `web/lib/board-entry.ts`; offline `localbench verify-submission`.

Hard rules unchanged: branch `codex/local-bench-online-backend`; `cli/runs/board/board_v1.json`
BYTE-IDENTICAL (do not touch); do NOT set any secret; do NOT push; do NOT deploy; private gate
stays. Everything builds + unit-tests locally WITHOUT R2 creds or the 3 secrets.

## Existing surface to reconcile (read these first)
- `web/functions/api/submissions/tickets.ts` (issue ticket), `.../submissions/[submissionId]/complete.ts`
  (finalize upload), `.../submissions/[submissionId].ts` (fetch), `.../admin/submissions.ts`,
  `.../admin/submissions/[submissionId]/decision.ts`, `.../admin/submissions/[submissionId]/verification.ts`,
  `.../suites.ts`, `.../suites/[suiteId]/manifest.ts`, `web/functions/_lib/api.ts`,
  `web/functions/_lib/suite-catalog.ts`, `web/functions/_middleware.ts` (the private gate — leave it).
- Board: `web/app/leaderboard/page.tsx`, `web/app/page.tsx`, `web/components/home-leaderboard.tsx`,
  `web/components/model-variant-board.tsx`, `web/components/board-scope-header.tsx`,
  `web/lib/leaderboard.ts`, `web/lib/board-entry.ts`.

## In scope for 2b

### 1. Reconcile the intake routes to the 3 contracts
- Tickets route issues a `submission_envelope_v1` (ticket_id, submitter_id, origin=`project_anchor`,
  allowed_schema=`localbench.result_bundle.v1`, expected_suite_release_id/sha256 nullable,
  accepted_suite_terms, max_upload_bytes, expiry, one_use, declared_model_slug, bundle_sha256 slot).
  Admin-gated by `ADMIN_API_SECRET` (binding stays UNSET in prod → route returns a clear
  disabled/503 when the secret is absent; unit-test with a test secret binding).
- Complete/finalize route records a `submissions` D1 row (status `uploaded`→`pending_verification`),
  idempotency by `raw_bundle_sha256` (UNIQUE — duplicate upload returns the same record, never a
  second row). It validates the uploaded bundle against `result_bundle_v1` shape (reject mismatched
  schema_version / removed fields).
- Admin decision/verification routes apply a verifier-produced status update
  (`localbench.submission_status_update.v1` from 2a's `verify-submission`): write
  `accepted_result_projection_v1` pointer + `validated_at`/validator provenance + flip status
  `accepted`/`rejected`; `publish_state` flip (`hidden`→`preview`→`published`) is a separate
  admin-gated step. D1 is index/pointers only — never scoring truth.
- Apply the 440f540 field renames everywhere the routes touch bundle/score fields (no `composite`,
  use `scores{}`; no submitter-authored `trust_tier`; `integrity.publishable`; etc.). Do not
  reintroduce removed fields.

### 2. R2 upload target
- Complete the request-upload path: a signed R2 PUT target (content-addressed key by
  `raw_bundle_sha256`) into the `localbench-submissions` bucket. Built + unit-tested against a mock
  R2 binding; LIVE function is gated on R2 creds (set later, NOT here). The full raw bundle goes to
  private R2; the accepted projection (board-safe) is the only public artifact.

### 3. Board partial-row rendering
- Render an `accepted_result_projection_v1` (mapped via `web/lib/board-entry.ts` → `board_entries`)
  as a board row that is HONEST about partial coverage: show per-axis scores + n, the
  `coverage_profile_id` (e.g. `partial-text-code-4axis-v1`), `headline_score` as `null`/"—"
  (NOT a number), `partial_composite` clearly labelled as partial (e.g. "0.7473 over 50% of headline
  weight"), `known_headline_contribution`, the missing-axis note (agentic), and a `rank_scope` badge
  — and DO NOT assign a `global_rank` to partial rows (rank-scoped or unranked only). Reuse/extend
  `board-scope-header.tsx` / `home-leaderboard.tsx` / `leaderboard.ts`.
- **Do NOT touch `board_v1.json`** (the frozen anchor board). Partial rows render from
  projections/D1, separate from the frozen anchor data.

## OUT of scope (later / gated)
Setting any secret; minting R2 creds; `wrangler deploy` / pushing; the GPU rerun; community accounts;
trust-tier machinery beyond conservative enum labels; an always-on verifier service; public
raw-transcript release; flipping `LOCALBENCH_SITE_PRIVATE`. The Python `verify-submission` (2a) stays
the authoritative verifier — do NOT build a Worker-side rescorer.

## Definition of done
- Branch `codex/local-bench-online-backend`. `board_v1.json` byte-identical (blob 3d058e60). No
  secrets, no push, no deploy.
- Tests: route unit tests (miniflare/vitest) for ticket issuance (incl. disabled-without-secret),
  complete+idempotency, admin status-update application, R2-presign against a mock binding, all
  against a local D1 (apply migration 0002); board partial-row rendering tests (partial row shows
  no global rank + coverage scope + headline_score null). Full `pytest cli\tests` (≥977) + web tests
  green. Optionally a no-D1 bridge test: validate→rescore→projection→board-row render.
- Concise change summary: files touched, which existing routes were reconciled + how, what still
  needs secrets/R2 creds to function live.

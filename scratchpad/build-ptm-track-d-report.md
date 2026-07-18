# Track D build report

Date: 2026-07-18
Branch: `ptm/track-d`

## Outcome

Implemented the feature-flagged, server-side GitHub OAuth account and attribution slice. Device codes are represented externally only by opaque handles; GitHub access tokens are used only for the immediate `/user` request and are not persisted; account-key binding requires a fresh Ed25519 proof over the GitHub user ID. Web OAuth remains sessionless and cookie-free.

## Commits

- `c8a151e` `feat(auth): add GitHub OAuth account binding`
- `80b8d47` `feat(submissions): add GitHub attribution plumbing`
- `043a762` `feat(site): show GitHub submitter attribution`

No commits were pushed.

## Files

- `web/migrations/0015_accounts.sql`
- `web/functions/_lib/github-oauth-api.ts`
- `web/functions/_lib/github-oauth-client.ts`
- `web/functions/_lib/github-oauth-common.ts`
- `web/functions/_lib/github-oauth-contracts.ts`
- `web/functions/_lib/github-oauth-device-api.ts`
- `web/functions/_lib/github-oauth-store.ts`
- `web/functions/_lib/github-oauth-web-api.ts`
- `web/functions/_lib/submission-contracts.ts`
- `web/functions/_lib/submission-lifecycle-api.ts`
- `web/functions/_lib/submission-pop.ts`
- `web/functions/_lib/submission-store.ts`
- `web/functions/_lib/submission-ticket-api.ts`
- `web/functions/_lib/community-live-board.ts`
- `web/functions/api/auth/github/callback.ts`
- `web/functions/api/auth/github/device/poll.ts`
- `web/functions/api/auth/github/device/start.ts`
- `web/functions/api/auth/github/start.ts`
- `web/lib/community-data.ts`
- `web/lib/community-live-schema.ts`
- `web/lib/community-live.ts`
- `web/lib/submission-lifecycle.ts`
- `web/components/community-detail.tsx`
- `web/components/community-leaderboard-row.tsx`
- `web/components/submissions-lifecycle.tsx`
- `web/components/submitter-chip.tsx`
- `web/tests/community-live-contract-bridge.test.ts`
- `web/tests/community-live-render.test.tsx`
- `web/tests/community-live.test.ts`
- `web/tests/github-oauth-attribution.test.ts`
- `web/tests/github-oauth-callback.test.ts`
- `web/tests/github-oauth-device.test.ts`
- `web/tests/github-oauth-test-support.ts`
- `web/tests/publish-then-moderate-board.test.ts`
- `web/tests/publish-then-moderate-test-support.ts`
- `web/tests/submission-migrations.test.ts`
- `web/tests/submission-test-support.ts`
- `web/tests/submissions-page.test.tsx`

No never-touch board data, launch-freeze, data-integrity, or blackbox files were modified.

## Verification

- `npm ci`: passed; 168 packages installed. npm reported 2 moderate audit advisories; dependency remediation was outside this track.
- `npm run test`: passed. Test files: **87 passed, 1 skipped, 88 total**. Tests: **514 passed, 1 skipped, 515 total**. Duration: 674.08 seconds.
- Isolated frozen publication acceptance gate: **1 passed, 6 skipped, 7 total**. Duration: 503.76 seconds.
- `npm run typecheck`: passed with zero TypeScript errors.
- `npm run build`: passed; Next.js generated 208 static pages.

## Deviations

No functional deviations from the workorder.

Two defensive additions were made within scope:

- Device polling uses an atomic D1 claim so concurrent requests cannot both consume the same opaque handle.
- Ticket, live-board, and lifecycle reads retain the legacy column set when migration 0015 is not present, preserving the existing 0.4.2 and frozen blackbox paths during rolling schema deployment.

## Incomplete

None.

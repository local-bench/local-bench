# Publish-Then-Moderate Track A Build Report

Date: 2026-07-18

Branch: `ptm/track-a`

Baseline: `110108ab3854c731a75042ee27ec4eb44cc33ec1`

## Outcome

Track A is implemented, including the binding red-team amendments and the authoritative unified-board attribution contract in design sections 6 and 12. The final test, typecheck, and production-build gates all pass. No never-touch path was modified, and nothing was pushed.

## Commits made

The implementation commits made before this report are:

1. `8aa8f341ced3e6fd0a1671da2f2e2b231a2bca8d` — `feat(submissions): publish verified community rows`
2. `839a7396499764f4f1b71b1f8e7de711c405c14e` — `feat(submissions): enforce automated ingest budgets`
3. `e0501104088f736d1a116b54b3659fdd0bdd3442` — `feat(submissions): expose public lifecycle listing`
4. `78e575c82c65806115be7e587c2c42d60a8f6630` — `test(web): bound vitest worker concurrency`
5. `50f7f1112748c1f65b674b9ea5bced12121025c5` — `fix(submissions): require PoP for group creation`

The documentation commit containing this report is necessarily excluded from the in-file hash list because a commit cannot contain its own final hash. Its hash and message are included in the completion handoff.

## Files changed

- `docs/foundations/unified-board-attribution-design-2026-07-18.md`
- `web/functions/_lib/community-live-board.ts`
- `web/functions/_lib/community-model-groups.ts`
- `web/functions/_lib/submission-admin-artifacts-api.ts`
- `web/functions/_lib/submission-api-support.ts`
- `web/functions/_lib/submission-api.ts`
- `web/functions/_lib/submission-complete-api.ts`
- `web/functions/_lib/submission-contracts.ts`
- `web/functions/_lib/submission-gc-api.ts`
- `web/functions/_lib/submission-lifecycle-api.ts`
- `web/functions/_lib/submission-moderation-api.ts`
- `web/functions/_lib/submission-pop.ts`
- `web/functions/_lib/submission-projection-validation.ts`
- `web/functions/_lib/submission-ptm-migration-api.ts`
- `web/functions/_lib/submission-rate-limit.ts`
- `web/functions/_lib/submission-state.ts`
- `web/functions/_lib/submission-store.ts`
- `web/functions/_lib/submission-ticket-api.ts`
- `web/functions/_lib/submission-upload-api.ts`
- `web/functions/_lib/submission-verification-api.ts`
- `web/functions/_lib/submission-verification-store.ts`
- `web/functions/_lib/submission-zt1-decision.ts`
- `web/functions/_lib/submission-zt1-store.ts`
- `web/functions/api/admin/board/rebuild.ts`
- `web/functions/api/admin/migrate-publish-then-moderate.ts`
- `web/functions/api/admin/submissions/[submissionId]/bundle.ts`
- `web/functions/api/admin/submissions/[submissionId]/display-name.ts`
- `web/functions/api/board/community.json.ts`
- `web/functions/api/submissions/list.ts`
- `web/tests/community-model-groups.test.ts`
- `web/tests/publish-then-moderate-admin.test.ts`
- `web/tests/publish-then-moderate-alarms.test.ts`
- `web/tests/publish-then-moderate-board.test.ts`
- `web/tests/publish-then-moderate-contracts.test.ts`
- `web/tests/publish-then-moderate-ingest.test.ts`
- `web/tests/publish-then-moderate-lifecycle.test.ts`
- `web/tests/publish-then-moderate-test-support.ts`
- `web/tests/publish-then-moderate-verification.test.ts`
- `web/tests/publish-then-moderate-zt1-refresh.test.ts`
- `web/tests/submission-contract-v2-complete.test.ts`
- `web/tests/submission-contract-v2-support.ts`
- `web/tests/submission-contract-v2-ticket.test.ts`
- `web/tests/submission-test-support.ts`
- `web/tests/submission-zt1-auto-publish.test.ts`
- `web/vitest.config.ts`
- `scratchpad/build-ptm-track-a-report.md`

## Installation and verification

All commands below were run from `web/`.

| Command | Result | Counts / evidence |
| --- | --- | --- |
| `npm ci` | PASS | 167 packages added. The audit reported 2 moderate vulnerabilities. |
| `npm run test` | PASS | Test files: 79 passed, 1 skipped, 0 failed (80 total). Tests: 474 passed, 1 skipped, 0 failed (475 total). |
| `npm run typecheck` | PASS | `tsc --noEmit`; 0 TypeScript errors. |
| `npm run build` | PASS | Next.js production build completed; 207/207 static pages generated and 0 build errors. |

The final full-suite run took 547.75 seconds. Before the group-creation PoP fix, its focused regression test was red because an unsigned request returned HTTP 201; after the fix, the focused group/ingest run passed 10/10 tests across 2 files.

## Deviations and implementation clarifications

1. The base A1 cache test requested that query-string variants reuse the bare-path cache entry. Binding red-team amendment R3 overrides that requirement: the route now returns HTTP 400 for any query parameter and uses the bare path as its fixed cache key for valid requests.
2. The base A2/A3 preview and bypass language is superseded by binding amendments R4 and R5. Publishable ZT-1 decisions now publish immediately when the four hard-hold alarms permit; the legacy preview/provisional path is not used for new decisions.
3. No `0015` migration was added. Existing migrations 0001–0014 already contain every table and column needed by Track A, so there was no new DDL to append. Those migrations were not edited.
4. `web/vitest.config.ts` now caps Vitest at four workers. The unbounded default repeatedly exhausted Miniflare proxy ports on this Windows host and produced cascading `EADDRINUSE` failures; the bounded full suite completed with all tests green while retaining file parallelism.
5. Section 12.2 requires proof-of-possession for community model-group creation even though the narrower R7 workorder text explicitly calls out only its rate limit. The endpoint therefore uses Ed25519 PoP with the canonical message `localbench.community_group_pop.v1\n<declared_model_name>\n<timestamp>` and the same ten-minute freshness window as submission tickets.
6. Language-server diagnostics were unavailable in this environment, so the exact required `npm run typecheck` / `tsc --noEmit` gate was used as the authoritative static check.
7. The two moderate `npm audit` findings from installation were not force-fixed because dependency upgrades were outside the Track A contract and could introduce unrelated changes.

## Protected-path and provenance audit

The baseline-to-HEAD path audit found no modifications under any never-touch path. Test identifiers and data introduced for coverage are explicitly marked `fixture` or `test`; no public-data fixture, run artifact, or provenance record was fabricated.

The supplied workorder `scratchpad/ptm-track-a-functions-workorder-2026-07-18.md` remains untracked, unmodified, and excluded from commits.

## Incomplete items

No Track A workorder item is incomplete. The only outstanding repository condition is the unrelated two-moderate-vulnerability audit finding noted above; it was intentionally left unchanged.

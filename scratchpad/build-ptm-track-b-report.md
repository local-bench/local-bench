# Publish-then-moderate Track B build report

Date: 2026-07-18

Branch: `ptm/track-b`

Base: `110108a`

## Outcome

Track B is complete. The site now consumes the strict live community-board contract, reconciles live rows per field, overlays live data across all required community surfaces, exposes the paginated public submission lifecycle, extends submission detail attribution, and provides catalog-only base-model family shells. The red-team amendments are implemented as the controlling requirements.

The frozen ranked-board data and never-touch paths remain unchanged. No fabricated data files were added.

## Implementation commits

- `cdac50cb924c0382cd78903f9c1d158fe81e4abf` -- `feat(community): add strict live board reconciliation`
- `f4abcf35349e795a344f7dca782e3b73cebd7b48` -- `feat(community): overlay live rows across site surfaces`
- `0781fc981a2693fa1403e97910d26cb297c00fa6` -- `feat(submissions): add public lifecycle view`
- `b3c24a173b82a9a8308b66dc7c71f4fc5dc88046` -- `feat(site): expose submission lifecycle routes`
- `1945dc8db658eb99e6ffb38c51b1d0f5739a2c25` -- `feat(models): add community family base shells`
- `fa728fe58f7680362ca26babb6663b54126b9afc` -- `fix(submissions): align lifecycle response contract`

This report is committed separately after its contents are finalized; its enclosing commit is intentionally not self-referenced because a commit cannot contain its own stable hash.

## Files changed

- `scratchpad/build-ptm-track-b-report.md`
- `web/app/community/model/[groupId]/page.tsx`
- `web/app/community/page.tsx`
- `web/app/methodology/page.tsx`
- `web/app/model/[slug]/page.tsx`
- `web/app/sitemap.ts`
- `web/app/submission/page.tsx`
- `web/app/submissions/page.tsx`
- `web/components/app-shell.tsx`
- `web/components/catalog-only-notice.tsx`
- `web/components/community-detail.tsx`
- `web/components/community-family-results.tsx`
- `web/components/community-leaderboard-row.tsx`
- `web/components/community-listing.tsx`
- `web/components/community-live-state.tsx`
- `web/components/home-leaderboard.tsx`
- `web/components/leaderboard-provenance.tsx`
- `web/components/submissions-lifecycle.tsx`
- `web/e2e/all-routes.spec.ts`
- `web/e2e/data.ts`
- `web/lib/community-data.ts`
- `web/lib/community-family.ts`
- `web/lib/community-links.ts`
- `web/lib/community-live.ts`
- `web/lib/community-live-schema.ts`
- `web/lib/data.ts`
- `web/lib/submission-lifecycle.ts`
- `web/lib/submission-status.ts`
- `web/tests/community-live-render.test.tsx`
- `web/tests/community-live.test.ts`
- `web/tests/family-spine.test.tsx`
- `web/tests/methodology-page.test.tsx`
- `web/tests/sitemap.test.ts`
- `web/tests/submissions-page.test.tsx`

## Verification

Setup:

- `npm ci` in `web/` -- PASS; 167 packages installed, 168 audited. npm reported 2 moderate dependency vulnerabilities; no dependency mutation was made because `npm audit fix` was outside scope.

Final required commands, all run from `web/`:

| Command | Result | Counts |
|---|---|---|
| `npm run test` | PASS | 75 test files passed, 0 failed, 1 skipped; 463 tests passed, 0 failed, 1 skipped |
| `npm run typecheck` | PASS | 0 TypeScript errors |
| `npm run build` | PASS | 208/208 static pages generated; 0 build errors |
| `npm run e2e -- e2e/all-routes.spec.ts` | PASS | 2 browser tests passed, 0 failed; every static route returned HTTP 200 without browser runtime failures |

Targeted green commands:

| Command | Result | Counts |
|---|---|---|
| `npx vitest run tests/submissions-page.test.tsx tests/sitemap.test.ts tests/methodology-page.test.tsx` | PASS | 3 files passed; 11 tests passed, 0 failed |
| `npx vitest run tests/family-spine.test.tsx tests/data.test.ts tests/model-page-community.test.tsx tests/model-page-lineage.test.tsx tests/model-page-trusted.test.tsx` | PASS | 5 files passed; 26 tests passed, 0 failed |
| `npx vitest run tests/submissions-page.test.tsx` | PASS | 1 file passed; 5 tests passed, 0 failed |
| `npm run e2e -- e2e/all-routes.spec.ts --grep "submissions renders"` | PASS | 1 browser test passed, 0 failed |

Expected red/failing iterations resolved during the work loop:

- Lifecycle TDD red: `npx vitest run tests/submissions-page.test.tsx tests/sitemap.test.ts tests/methodology-page.test.tsx` failed before the lifecycle module/routes/disclosure existed; the same selection later passed 11/11.
- Family-spine TDD red: `npx vitest run tests/family-spine.test.tsx` failed as expected because the new component/helper did not exist; the implemented family selection later passed in the 26/26 targeted selection.
- Coordinated lifecycle-contract red: `npx vitest run tests/submissions-page.test.tsx` produced 1 pass and 4 failures after fixtures were changed to the authoritative flat timestamp fields and `metadata_unsafe`; the client correction then passed 5/5.
- First complete browser run: `npm run e2e -- e2e/all-routes.spec.ts` produced 1 pass and 1 failure because the assertion expected `/submissions` while the static export canonically rendered `/submissions/`; the corrected final run passed 2/2.
- One complete `npm run test` attempt produced 429 passes, 34 failures, and 1 skip because a concurrent Track C pytest process owned localhost ports 49152-49153, causing Miniflare `EADDRINUSE` failures. After that unrelated process exited and the ports were verified free, the unchanged final command passed 463/463 with 1 skip.
- Earlier full-suite wrappers timed out before Vitest emitted totals. Their exact test counts were unavailable, so they are not represented as completed test runs.

Manual visual QA:

- Desktop Chromium capture at 1280x720: clean navigation, hierarchy, fallback panel, and footer.
- Mobile Chromium capture at 390x844: navigation wrapped without overlap; page copy, unavailable state, and footer remained readable with no horizontal clipping.
- The generated screenshots, Playwright report, traces, debug journal, temporary server, and synthetic black-box fixture were removed after inspection.

Frozen-path audit:

- `web/public/data/index.json`: `a880d031d4539b031f2bc5d51907b21bec896eac7c4cc7eca6ca5173113637cf`
- `web/components/launch-freeze.ts`: `70681ffdf985bddd97574908f6a69f06c593828c0dd6e93903a739cd936c4264`
- `web/tests/data-integrity.test.ts`: `2599288d68102207adf324bbe9c51218c0efe8e5d33e4956d3381704bffc5ebc`
- `web/tests/publication-blackbox-gate.test.ts`: `c34cce8bdb9eed1f543c0843b5fee76faf42276d5020631544cd3694707f766d`
- Aggregate `web/public/data/models/**` + `web/public/data/runs/**`: `a3acaf2569e86aa2d60393fb8390da01edd881d373bf5bdb8414f6cb282d69bf`
- `cli/**`: no changed paths.

All hashes match the pre-implementation baseline.

## Deviations from the workorder

None.

The base B2 queue/feed stitching description was intentionally not implemented because binding red-team amendment R4 replaces it with the single paginated `GET /api/submissions/list?cursor=` source. Live-only detail links are intentionally suppressed per R3, and no client-side suppression-list fetch was added per R6.

The connected in-app browser was unavailable during visual QA, so the repository's installed Playwright/Chromium runner was used. This changes only the verification mechanism, not any deliverable.

## Incomplete

Nothing incomplete. No push was performed.

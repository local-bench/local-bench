# Track E build report

Date: 2026-07-18 (Australia/Brisbane)

Branch: `ptm/track-e`

Base: `9d21688`

Status: complete

## Outcome

Track E now presents one unified board on both `/` and `/leaderboard`. Ranked and
community rows share one sortable/filterable table, default to descending composite
order, retain ranked positions 1–5, and show the community trust tier in the rank cell.
Live community rows retain reconciliation, suppression, freshness, and measured-axis
coverage behavior on both pages. Community discovery was removed from navigation and
the sitemap while `/community` and `/community/model/[groupId]` remain functional for
deep links.

## Implementation commits

- `07a0fea feat(board): interleave community rows`
- `6dbb8b8 feat(home): show unified leaderboard`
- `51225a8 fix(nav): remove community discovery links`
- `1c91913 test(e2e): cover unified board surfaces`
- `6065b2a fix(home): contain mobile onramp grid`
- `ae20db7 fix(board): normalize community composite scale`
- `7398161 fix(board): cue mobile horizontal scrolling`
- `2ed45bb fix(ui): clarify responsive overflow affordances`
- `de0f55b fix(board): normalize community axis sorting`

## Files changed

- `web/app/page.tsx`
- `web/app/sitemap.ts`
- `web/components/app-shell.tsx`
- `web/components/benchmark-model-picker.tsx`
- `web/components/benchmark-onramp.tsx`
- `web/components/board-index-chart.tsx`
- `web/components/community-leaderboard-row.tsx`
- `web/components/home-leaderboard.tsx`
- `web/components/leaderboard-table.tsx`
- `web/e2e/home.spec.ts`
- `web/e2e/leaderboard.spec.ts`
- `web/lib/leaderboard-sort.ts`
- `web/lib/unified-leaderboard.ts`
- `web/tests/community-pages.test.tsx`
- `web/tests/homepage-community.test.tsx`
- `web/tests/leaderboard-index-chart.test.tsx`
- `web/tests/sitemap.test.ts`
- `web/tests/unified-leaderboard.test.tsx`

The workorder itself remained untracked and was not committed. No never-touch path was
modified: frozen board data, launch-freeze code, model/run JSON, data-integrity tests,
and the publication black-box gate are unchanged.

## Verification

- Fresh install: `npm ci` completed in `web/`; 167 packages installed. npm reported
  2 moderate audit advisories; no audit mutation was performed.
- Unit/integration suite: `npm run test` passed on final implementation commit
  `de0f55b` in 547.48 seconds.
  - Test files: 85 passed, 1 skipped (86 total).
  - Tests: 505 passed, 1 skipped (506 total).
- Static typing: `npm run typecheck` passed with zero TypeScript errors.
- Production build: `npm run build` passed with Next.js 16.2.9; compilation and
  TypeScript succeeded and 208/208 static pages were generated.
- Browser regression suite: `npx playwright test e2e/home.spec.ts e2e/leaderboard.spec.ts`
  passed 4/4 Chromium scenarios in 16.3 seconds.
- Manual browser QA covered `/` and `/leaderboard` at 375, 768, and 1280 px:
  document width remained contained at every breakpoint; the unified table showed
  6/5/1 rows for All/local-bench/community; table and chart scroll affordances appeared
  at the widths where needed; and the mobile model picker no longer collapsed.
- A live-overlay browser fixture verified a re-scored community row at 57.0 sorted
  above the ranked 53.1 row, a `4/6 axes` marker, and freshness/reconciliation on both
  pages. `/community` and its published detail route both returned HTTP 200.
- Two final independent visual-QA reviewers returned `PASS` after inspecting all six
  responsive captures and the final relevant source changes. Temporary screenshots,
  traces, servers, and the debugging journal were removed after review.
- Repository audit: `git diff --check` passed; protected-path diff and unsafe TypeScript
  escape-hatch scan were empty.

## Deviations and implementation notes

- No requested behavior was omitted or changed.
- Actual ranked scores are stored on a 0–100 scale while community publication scores
  are 0–1. Composite and live per-axis community values are normalized to 0–100 only
  for unified display sorting; ranked scoring and frozen bytes remain untouched.
- Responsive QA found two adjacent presentation defects in the newly unified surface:
  the homepage on-ramp could expand the mobile document, and a model-picker action row
  could collapse. The implementation adds bounded grid/flex behavior plus explicit
  scroll cues for the intentionally wide table/chart.
- Some intermediate full-suite attempts encountered Windows loopback port exhaustion
  (`EADDRINUSE`) while other worktrees were testing. The final isolated command above
  passed twice with identical 505-passed/1-skipped totals; the reported 547.48-second
  run is the one bound to `de0f55b`.

## Incomplete items

None.

No push was performed.

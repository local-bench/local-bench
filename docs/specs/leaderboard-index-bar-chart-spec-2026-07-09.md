# Leaderboard Index bar chart — spec v2 (2026-07-09, post-red-team; amendments at bottom are BINDING)

Owner ask (Michael): the /leaderboard page should open with a bar chart ranking ranked rows by
Local Intelligence Index, highest → lowest, inspired by artificialanalysis.ai/#intelligence but
in local-bench's own visual language. It must update automatically as the board updates (i.e.
driven by the same generated index payload as the tables — no new data pipeline).

Owner decisions (AskUserQuestion, 2026-07-09):
- **Rows: every ranked variant** — the chart mirrors the ranked table directly below it (one bar
  per ranked run, quant label shown). NOT best-per-model (that view lives on the home page).
- **Bar style: axis-stacked** — each bar is composed of the six weighted axis contributions in
  the canonical axis palette (AXIS_CONFIG), same visual language as IndexContributionRail and
  the CLI's colored progress bar.

## Architecture

1. **New shared helper `web/lib/axis-contributions.ts`** (refactor, do first):
   - `indexContributions(axes: Record<string, AxisScore>): readonly { key, label, color, contribution }[]`
     computing weight × axis.point per canonical axis, plus `contributionTotal(...)`.
   - Weights live here as the single exported source (`INDEX_AXIS_WEIGHTS`), and
     `IndexContributionRail` in `components/score-bar.tsx` is refactored to consume this helper
     (behavior-identical: same segment order, same title string, same widths).
   - Do NOT change how build_data computes composites; this is presentation-side only.

2. **New server component `web/components/board-index-chart.tsx`**:
   - Props: `models` — the exact `ranked` array from `splitLeaderboard(index.models)` that the
     page already computes (no new data fetch, no client JS unless unavoidable; precedent:
     best-variant-scatter and quality-vram-scatter are server-rendered inline SVG).
   - Renders `null` when `models.length === 0` (page already has empty-state copy).
   - Placement in `app/leaderboard/page.tsx`: directly under the header grid, above
     `<HomeLeaderboard models={ranked} .../>`.

## Visual spec

- Vertical bars, sorted by `composite.point` desc (same ordering as the ranked table).
- **Bar = stack of six axis contributions**, bottom-up in AXIS_CONFIG order, colored with
  `axisColor(key)`. Segment heights are proportional shares of the bar's total height, where the
  bar's total height maps `composite.point` on the y scale — i.e. scale the raw contribution sum
  to equal composite.point so the drawn bar never visually disagrees with the printed score
  (bootstrap composites can differ from the naive weighted sum by rounding).
- **CI whisker** per bar from `composite.lo`–`composite.hi` (thin line + caps, `bench-muted`).
  This is a differentiator vs AA and matches the site's honesty posture.
- **Value label** above each bar: `formatScore(composite.point)` in mono.
- **X labels** below each bar: model label (linked to `/model/<slug>`) + quant label in mono
  muted small text. Labels wrap to two lines max; no rotation if avoidable at target widths.
- **Y axis**: 0–100 fixed scale (Index is 0–100; fixed scale keeps charts comparable across
  rebuilds), light horizontal gridlines every 20, mono tick labels.
- **Legend**: one row of the six axis chips (dot + label), reusing the AxisDot pattern from
  best-variant-table.
- **Header**: eyebrow "Full board", h2 "Local Intelligence Index — ranked", one plain-language
  muted sentence. NO index-version/qualifier jargon (the page header above already stamps it).
  Keep copy plain per the 2026-07-09 jargon sweep.
- Site style: bench-panel card, bench-line borders, rounded-lg, same as sibling sections.

## Behavior / scaling

- Bars: fixed max width (~72px) and min width (~40px); the SVG viewBox width grows with row
  count and the container is `overflow-x-auto` (site-wide precedent) so 30+ rows scroll
  horizontally rather than crush. With 1–3 rows the chart stays left-aligned at max bar width —
  do not stretch three bars across the full panel.
- "Dynamic" requirement: satisfied by construction — the component renders from the generated
  index payload at build time, exactly like the tables; every deploy/rebuild updates it. No
  client-side fetching.
- Hover: `<title>` tooltip per bar with the full contribution breakdown (reuse the rail's title
  text format) — no JS tooltip library.

## Accessibility

- SVG `role="group"` with a meaningful `aria-label` ("Bar chart of N ranked variants by Local
  Intelligence Index, highest X lowest Y") — matches the a11y pattern applied to the scatters on
  2026-07-08 (role img → group).
- The ranked TABLE below is the accessible data alternative; add an sr-only sentence saying so.
- Text contrast: value labels `bench-text`, axis labels `bench-muted` (existing tokens pass the
  axe checks we ran 07-09).
- Links inside SVG are real anchors (foreignObject NOT required — use `<a>` wrapping SVG rects
  or render x-labels as HTML below the SVG; prefer HTML labels outside the SVG for focus order
  and wrapping. Implementation may choose SVG-only bars + HTML label row grid-aligned under
  them, as long as alignment holds at all widths).

## QA gates (all must pass before deploy)

- Unit tests: contribution helper (weights sum to 1, per-axis math, missing axes → 0-height
  segment not NaN); component (renders one linked bar per ranked row, desc order, whisker
  coords match lo/hi, null on empty input, no bar exceeds the 100 gridline).
- Refactored IndexContributionRail: existing tests stay green; rendered title string identical.
- `npx vitest run` full, `npx tsc --noEmit`, `npm run build` (197 pages), zero new axe
  violations on /leaderboard (re-run web/a11y-audit.mjs).
- Visual check on the built page at 3 rows (today's board) and a synthetic 20-row fixture test.
- No build_data/, functions/, LAUNCH_FREEZE, or CLI changes. web/ only.

## Out of scope (v1)

- Interactive filtering/toggles (AA has metric switchers; our v1 is one metric — the Index).
- Animations.
- Family grouping/coloring (axis stacking already encodes composition; family color would fight
  the palette).

## v2 AMENDMENTS — GPT-5.5 xhigh red-team 2026-07-09, ALL BINDING

1. **(HIGH) Score source = `scoreForMode(model, "full")`, not `composite`.** `splitLeaderboard`'s
   ranked rows are admitted via `isFullIndexRow`, which accepts `composite_full ?? composite`;
   the table renders through `scoreForMode`. The chart must compute
   `const score = scoreForMode(model, "full")` once per row and use it for sorting, bar height,
   value label, CI whisker, and tooltip. Test fixture required: `composite` null +
   `composite_full` non-null renders correctly and matches table order.
2. **(MED) Incomplete canonical axes must not be silently rescaled to look complete.** Only
   rescale contribution segments to the score when ALL six canonical axes are present. If any
   canonical axis is missing, render the measured contributions at their raw weighted heights
   plus a neutral "unallocated" remainder segment (bench-muted at low opacity) up to the score,
   with the tooltip naming the missing axes. Never inflate measured segments.
3. **(MED) Geometry sanitization.** All contribution inputs: non-finite → 0, negative → 0.
   Clamp all y-scale inputs (score point, lo, hi, segment tops) to [0,100] (use/extend
   `clampScore`). If contribution total <= 0: no division — render an empty stack (no segments)
   with the score still shown as text and whisker still drawn from clamped lo/hi.
4. **(MED) Exactly ONE focusable link per row.** The HTML label under the bar is the anchor to
   `/model/<slug>`; SVG bars are non-focusable (`aria-hidden` on the bar rect group is fine
   given the sr-only table pointer). Render test asserts exactly one `/model/<slug>` anchor per
   ranked row.
5. **(MED) Tooltip must match the site's CSS-only pattern, not bare `<title>`.** Reuse the
   `group`/`group-hover` (+ focus-within) visible tooltip approach from
   quality-vram-scatter/best-variant-scatter for the per-bar contribution breakdown, with an
   enlarged hover hit target. `<title>` may exist in addition, never alone.
6. **(LOW) One inner scroller surface.** A single explicit-width inner element inside the
   `overflow-x-auto` scroller contains BOTH the SVG and the HTML label row, laid out on the same
   slot grid (`slotWidth` for spacing, `barWidth` <= slotWidth for the rect) so alignment cannot
   drift. Fixtures at 1, 3, and 40 rows must keep bar centers and label centers within the same
   slot.
7. **(LOW) Test conventions.** `web/tests/leaderboard-index-chart.test.tsx` using
   `renderToStaticMarkup` + schema-parsed fixtures (`IndexModelSchema.parse`), covering: the
   `scoreForMode` fallback fixture, zero/negative contribution totals, partial canonical axes
   (amendment 2 behavior), one-anchor-per-row, 1/3/40-row slot-width invariants, tooltip +
   focus markup presence, desc ordering, and null-on-empty. Contribution-helper unit tests:
   weights sum to 1 and match `IndexContributionRail`'s historical output (title string
   byte-identical on a fixed fixture).

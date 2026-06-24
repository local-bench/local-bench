# Landing-page layout re-org + "time to complete" — design

**Date:** 2026-06-23
**Branch:** `suite/v1-quant-wedge`
**Status:** design, pending review

## Context

The landing page (`web/app/page.tsx`) currently stacks four sections in this order:
Rig-Match Finder → Quality-vs-VRAM scatter → best-variant summary table → full detailed
leaderboard. We want the graph + summary to lead, the heavy detailed table to move off the
landing onto its own page, and a user-facing latency ("time to complete") number on both boards.

## Goal / scope

1. Re-order the landing page so the **graph** and **summary board** are the hero.
2. Move the **full detailed leaderboard** to a new `/leaderboard` page.
3. Add a **"Time/answer"** (per-answer latency) column to **both** the summary and detailed boards.
4. Surface **total run time** more prominently on the run-detail page (already present as `wall-time`).

Out of scope: changing scoring/axes; per-item precise latency timing; p95 latency; adding API
anchors as summary rows; the separate pending rewrite of `cli/tests/test_web_build_data.py`.

## Decisions (from brainstorming)

- **Landing order:** Graph → Summary board → Rig-Match Finder → "View full leaderboard →" CTA.
- **Detailed board:** moves to `/leaderboard` (verbatim, with its ranked/lane caveat + header copy).
- **"Time to complete" = per-answer latency** on the boards; **total run time** on the run-detail page.
- **Nav:** keep `Leaderboard → /`; add a new `Full board → /leaderboard` item.
- **Detailed board column:** add `Time/answer` **beside** the existing `Tokens` column (keep both).
- **Summary board scope:** unchanged — measured **local** models only (best variant each); API
  frontier models remain ceiling lines on the graph, not rows.

## Latency: definition & data flow

`latency_s_median = tokens_to_answer_median ÷ tok/s` — the estimated median seconds to generate
one answer (includes reasoning/thinking tokens, since these are capped-thinking runs). It is an
estimate measured on the test rig; the UI labels it as a guide, not a guarantee.

**Computed once at build time** (both inputs are already in hand in `build_data.py::_build_run`):
`None` when `tokens_to_answer_median` is null or `tok/s` is null/≤0. Emitted onto the measured
`index_row` (→ `IndexModel`) and `model_row` (→ `ModelRun`). Catalog shells and demo rows omit it
(schema field is optional/nullable → renders as "—").

Plumbing for the summary board:
`model_row.latency_s_median` → `toRigMatchCandidate` → `RigMatchCandidate.latencySMedian`
→ `selectBestVariantPoints` → `BestVariantPoint.latencySMedian`.

## Affected files

**Data layer**
- `web/build_data.py` — compute `latency_s_median`; add to the `model_row` and `index_row` dicts.
- `web/lib/schemas.ts` — add `latency_s_median: z.number().nullable().optional()` to
  `IndexModelSchema` and `ModelRunSchema`.
- `web/lib/data.ts` — `toRigMatchCandidate`: pass `latencySMedian: run.latency_s_median ?? null`.
- `web/lib/rig-match.ts` — add `latencySMedian: number | null` to the `RigMatchCandidate` type.
- `web/lib/best-variant.ts` — add `latencySMedian` to `BestVariantPoint` + carry it in
  `selectBestVariantPoints`.
- `web/lib/format.ts` — a latency formatter → `~13 s` / `~1.4 min` / `—` for null. Reuse
  `formatSeconds` if its compact output fits; otherwise add `formatLatencySeconds`.

**Components / pages**
- `web/app/page.tsx` — reorder to scatter → summary table → finder → CTA; remove the
  `HomeLeaderboard` section (and its `axisCopy`/`hasMeasuredRankedData` block moves to /leaderboard).
- `web/app/leaderboard/page.tsx` — **new**; renders the "Full leaderboard" header copy, the
  ranked/lane caveat box, and `HomeLeaderboard`. Uses `getHomePageData`/`getIndexData`.
- `web/components/best-variant-table.tsx` — add `Time/answer` column after `tok/s`.
- `web/components/home-leaderboard.tsx` — add a sortable `Time/answer` column beside `Tokens`
  (header + cell + `compareRows` case `latency`).
- `web/components/app-shell.tsx` — add `Full board → /leaderboard` nav link.
- `web/app/run/[runId]/page.tsx` — relabel `wall-time` → "Total run time" and lift it into the
  header stat block (keep the manifest entry).

**Tests**
- `web/tests/data.test.ts` — assert the landing no longer renders `full-leaderboard` and the new
  page does; assert measured models carry a numeric `latency_s_median`.
- `web/e2e/*.spec.ts` — point any `full-leaderboard` assertion at `/leaderboard`.
- (Note: `cli/tests/test_web_build_data.py` is already failing and owned by the benchmark agent;
  the latency field adds one more thing for that rewrite. Not touched here.)

## Risks / notes

- The detailed table gets ~90px wider (Time/answer beside Tokens); it already scrolls horizontally.
- Latency is hardware-specific and an estimate — must be labelled as such in both boards.
- Moving the board off `/` changes the home `data-testid="full-leaderboard"` location; tests must
  follow it (above).
- No data is republished by this change beyond the new `latency_s_median` field; composites/axes
  are untouched.

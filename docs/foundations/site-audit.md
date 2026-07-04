# local-bench — Front-End Site Audit

*Auditor: Claude (read-only, no server run) · Date: 2026-06-13*
*Reference docs: PROJECT-HANDOFF.md §1/2/6, website-design.md (full)*

---

## 0. What was audited

All source files under `web/` were read in full:

- **Routes:** `app/page.tsx`, `app/layout.tsx`, `app/model/[slug]/page.tsx`, `app/run/[runId]/page.tsx`, `app/methodology/page.tsx`, `app/trust/page.tsx`
- **Components:** `components/home-leaderboard.tsx`, `components/model-scatter.tsx`, `components/run-axis-breakdown.tsx`, `components/score-bar.tsx`, `components/badges.tsx`, `components/detail-grid.tsx`
- **Lib:** `lib/schemas.ts`, `lib/data.ts`, `lib/format.ts`
- **Config/styling:** `tailwind.config.ts`, `app/globals.css`, `next.config.mjs`
- **Data pipeline:** `build_data.py`, `data_sources.json`, `public/data/` (output structure)
- **Tests:** `tests/data.test.ts`, `e2e/home.spec.ts`, `e2e/model.spec.ts`
- **Reference:** AA homepage fetched for pattern comparison

---

## 1. Per-dimension gap analysis

### 1.1 Visual design system & polish

| | Detail |
|---|---|
| **What exists** | Seven `bench.*` Tailwind tokens in `tailwind.config.ts`: `bg/#0b0e14`, `panel/#11161f`, `line/#273244`, `text/#eef4fb`, `muted/#99a7b8`, `accent/#32d2b4`, `anchor/#f6b24b`. Font families wired as CSS vars (`--font-sans: Aptos/Segoe UI Variable`, `--font-mono: Cascadia Mono`). Dark-only with a subtle three-stop gradient on `body`. `::selection` teal tint. |
| **Missing / weak** | **14 tokens defined in the spec are absent from tailwind.config.ts**: `panel-2`, `line-strong`, `muted-2`, `accent-dim`, `anchor-soft`, `better/#46d39a`, `worse/#ff6b6b`, `tied`, `mixed/#c792ea`, `lane-reasoning-edge/#7c83ff`, `warn`, plus the quant-verdict semantic layer entirely. Without these tokens the QuantDeltaStrip and dominance-verdict chips cannot be built to spec without magic-stringing hex values. The chart SVGs hardcode hex values directly (`stroke="#32d2b4"`, `fill="#f6d08d"`, etc.) rather than using CSS vars — a token regression waiting to happen. No `panel-2` depth level means inset wells (methodology, run-detail nested sections) can't use the three-surface depth model without ad-hoc Tailwind opacity tricks. Typography scale from the spec (display 2.5rem → micro 0.6875rem, tabular-figures mono for every number) is partially present but not enforced via Tailwind `fontSize` config — implementers must eyeball it. The H1 on the home page uses `text-4xl` which is Tailwind default (2.25rem), not the 2.5rem display scale in the spec. No `index_version` anywhere (the spec requires `suite-v{n} · index-v{n}` on every page; only `suite_version` is shown). |
| **Severity** | High — the incomplete token set means every new component (QuantDeltaStrip, DiagnosticsPanel, verdict chips) will accumulate hardcoded hex literals or be built using mismatched approximations. |
| **Recommendation** | Extend `tailwind.config.ts` with all 14 missing semantic tokens before any new component work. Refactor the existing SVG hex literals to CSS vars / Tailwind `theme()` calls. Add the typography scale as named sizes. Add `index_version` to both the schema and the index JSON build step. |

---

### 1.2 Information architecture & navigation

| | Detail |
|---|---|
| **What exists** | 3-level IA is structurally present: `/` → `/model/[slug]` → `/run/[runId]`, plus `/methodology` and `/trust`. Back-links exist (model → leaderboard, run → model). The `/methodology` and `/trust` links appear in the home page nav. |
| **Missing / weak** | **`/submit` page is entirely absent** — no file, no route, no stub. The **TopNav / AppShell** described in the spec does not exist: there is no persistent navigation bar across pages. Each page has its own one-off nav link cluster. The `/methodology` and `/trust` links appear only on the home page header `<nav>` — they are invisible from model and run-detail pages. The `VersionStamp` (suite+index version, shown on every page) is only partially present: home page shows the suite version inline as a `<p>` tag, but methodology and trust pages show no version at all. The home page header shows `suite-v0 methodology` on the methodology page (line 11 — hardcoded string, wrong version label). Breadcrumb trail (`Home > Model > Run`) is missing. |
| **Severity** | High — the missing `/submit` page is a core feature gap (the contribution funnel). The missing global TopNav means the trust/methodology pages are not reachable from any page except home. |
| **Recommendation** | Build a persistent `AppShell` + `TopNav` used in `layout.tsx` so all pages share nav. Add `/submit` as a stub at minimum. Add breadcrumb component to model and run pages. |

---

### 1.3 Charts / data-viz quality

| | Detail |
|---|---|
| **What exists** | Two hand-rolled SVG charts: `ModelScatter` (per-model quality-vs-VRAM) and `RunAxisBreakdown` (per-axis CI whisker bars). CSS-bar `ScoreBar` + `AxisMiniBar` for the table. The scatter has: correct anchor reference dashed lines with label de-collision (`layoutAnchors`), CI whiskers on community points (I-bars with caps — lines 90–96 of model-scatter.tsx), X-domain with 8% padding, Y gridlines at 0/25/50/75/100. The axis breakdown uses a teal glow point marker and translucent CI band (run-axis-breakdown.tsx lines 51–60). Both use SVG `role="img"` and `aria-label`. |
| **Missing / weak** | **The scatter is only on the model page — it is NOT on the home page as the hero** (the spec's most important layout change). Home currently opens directly to the table with no chart above it. The VRAM-tier guide verticals (8/12/16/24/32/48 GB lines labeled "what fits my card") are absent. No **log-scale toggle** on the X axis. No **lane segmented control** on the scatter. No **tooltips** — hovering a point shows nothing (SVG only, no hover cards). Anchor points have no whiskers (correct per spec, but their hover tooltip with the anchor's own CI is also missing). The scatter X-axis shows only min/max labels with no intermediate ticks. The `~chance` hatched marker (for CI-crossing-chance points) is not implemented — scores below chance just render as regular teal dots. The `AxisMiniBar` in the table shows a score and CI text but no `~chance` substitution when CI crosses chance. No **radar toggle** on the per-axis profile. No `QuantDeltaStrip` chart exists at all (the launch hero). No `DiagnosticsPanel`. The SVG hardcodes `WIDTH=900, HEIGHT=420` with no responsive fluid sizing — it uses `min-w-[760px]` with `overflow-x-auto` which prevents true narrow-screen rendering. |
| **Severity** | Critical — the home hero scatter is absent (home opens to raw table, not the wedge visualization); the QuantDeltaStrip (the launch differentiator) does not exist at all. |
| **Recommendation** | (1) Promote ModelScatter (or a variant) to home as `QualityVsVramScatter` hero above the table — this is the single highest-visual-impact change. (2) Build `QuantDeltaStrip` for the model page. (3) Add tooltip/hover cards to scatter points. (4) Add VRAM-tier guide verticals. (5) Implement `~chance` hatching. |

---

### 1.4 Home leaderboard

| | Detail |
|---|---|
| **What exists** | `HomeLeaderboard` component with sortable columns, `RankMarker` (shows "Unranked" for all rows since all current runs are Quick/non-ranked), `KindBadge`, `TierBadge`, `LaneBadge`. Per-axis mini-bars for the 3 current axes. Tokens/cost columns. Lane-caveat banner (amber box, correctly positioned). Anchor rows tinted amber via `bg-amber-300/[0.025]`. Correct `buildLaneRanks` logic for within-lane ranking. |
| **Missing / weak** | Hardcoded 3 axes (`TABLE_AXES = ["mmlu_pro", "ifeval", "genmath"]` at line 10 — the primary axis-flexibility problem, addressed in §1.9). No **FilterBar** — no community/anchor toggle, no lane filter, no tier filter, no VRAM-budget slider, no search input. No **ReplicatedBadge** (the `replicated` field exists in the schema but no badge component renders it). The `~chance` substitution is missing in `AxisMiniBar` — a near-chance score renders as a number, not the `~chance` marker. The composite `ScoreBar` does not show a CI band (only point + CI text in a separate `<span>`). The `AxisMiniBar` CI display is asymmetric — it shows `±X.X` text but the mini-bar only shows the point magnitude, not a CI band over the bar. No `DominanceChip`. The description still says "MMLU-Pro, IFEval, and genmath" (home page.tsx line 24 — hardcoded to old suite). |
| **Severity** | High — the hardcoded axes are a P0 blocker for the suite-v1 transition. The missing FilterBar is a High gap as dataset grows. The stale description text is a trust/honesty issue. |
| **Recommendation** | See §1.9 for the axis refactor. Immediately fix the stale description copy. Add ReplicatedBadge. Plan FilterBar as a dedicated build task. |

---

### 1.5 Model page

| | Detail |
|---|---|
| **What exists** | Model page renders: `KindBadge`, H1 model label, `ModelScatter` (VRAM scatter vs anchors), a runs table with quant/footprint/composite/per-axis/tier/lane/tokens/tok_s/cost/hardware columns. Back-link to leaderboard. |
| **Missing / weak** | **`QuantDeltaStrip` is entirely absent** — this is the launch hero for the model page and the primary differentiator. The model page currently has no decomposition of quant cost at all. No **`PerAxisProfile`** section (bars or radar for the best run's per-domain profile). No **lane segmented control** on either the scatter or the profile. No **`ReportedShelf`** (reported-elsewhere benchmarks). The runs table shows per-axis scores as plain numbers (no `AxisMiniBar`, no CI bands — compare to home table which at least uses `AxisMiniBar`). The `worst_axis` field is computed in `RunDetailSchema` but not used on the model page (it's only used in `RunAxisBreakdown`). No `VersionStamp` component (model page header shows no suite version). |
| **Severity** | Critical — the QuantDeltaStrip is the product wedge. A model page without it has no differentiation from a simple runs table. |
| **Recommendation** | Build `QuantDeltaStrip` as the first new component for the model page. Add `PerAxisProfile` using the existing `RunAxisBreakdown` logic generalized to a model's best run. Add `ReportedShelf`. Add `VersionStamp` to header. |

---

### 1.6 Run detail page

| | Detail |
|---|---|
| **What exists** | Strong implementation: 60px composite headline, CI text, `RunAxisBreakdown` with worst-axis amber highlight (the CI bar + glow marker), `ManifestCard` (DetailGrid with 14 fields covering model/quant/runtime/hardware/os/lane/thinking_mode/caps/sampling/tokens/tok-to-answer/tok_s/wall-time/cost/n_items/n_errors/n_no_answer), provenance section with SHA256 hashes per bench. Data-quality note (conditional amber box for errors/no-answer). Back-link to model. Suite version shown as `<p>` in header. |
| **Missing / weak** | **No contamination canary section** (`{public_score, private_score, gap}` — the spec's trust primitive for run detail). **No conservative-ranking note** for thin coverage (μ−3σ display). **No `AxisRungBreakdown`** — the current `RunAxisBreakdown` shows per-axis totals but not per-rung sub-scores (e.g., SuperGPQA easy/middle/hard, BFCL simple/multiple/parallel). The `ranked: false` flag exists in `IndexModel` but there is no UI note on the run page when conservative ranking was applied. The data-quality note renders errors + no-answer items but lacks the `~chance` threshold check. `index_version` is absent from the run header (only `suite_version` shows). The sampling formatter at run-detail line 133–137 iterates `AXES` to build by-bench sampling text — this is hardcoded to 3 axes and will silently omit new benches. |
| **Severity** | Medium — the contamination canary is a key trust primitive but requires schema additions first. The rung breakdown is High once suite-v1 data exists (rung scores don't exist in current data). |
| **Recommendation** | Add contamination canary section (schema + UI together). Add `index_version`. Fix `formatSampling` to be axis-agnostic. Plan `AxisRungBreakdown` as a suite-v1 follow-on. |

---

### 1.7 Methodology / Trust pages

| | Detail |
|---|---|
| **What exists** | Both pages exist with correct prose covering the key concepts: three estimands, chance-corrected normalization (mentions MMLU-Pro 10% baseline, IFEval/genmath zero), lanes/tiers, bootstrap CIs, editorial versioning (methodology). Trust page covers community-reported/replicated/anchor labels, cheat-proxy attack, replication as trust unit. Correct visual treatment (dark palette, `text-bench-muted` prose, `text-bench-text` headings). |
| **Missing / weak** | **Methodology hardcodes suite-v0** ("suite-v0 methodology" at line 10 — will be wrong when suite-v1 ships). The spec's **`DiagnosticsPanel`** (anchor-spread bars, S_index gauge, discrimination strip) — the primary credibility moat vs AA — does not exist. The **`WeightsTable`** (index-v2 weights per domain/bench) does not exist. The normalization explanation mentions only 3 benches by name (MMLU-Pro, IFEval, genmath — will be stale). The **per-bench chance baseline table** is absent. The trust page's label definitions are prose-only — no `KindBadge`/`ReplicatedBadge` visual cards as the spec specifies. The "three estimands" section correctly describes them but gives no examples or data. No `index_version` on either page. Both pages are pure static text — no structured data-driven content (the weights table, diagnostics, and badge cards all need data). |
| **Severity** | High — the DiagnosticsPanel is the credibility moat the spec identifies. Its absence means the site cannot currently make its "we publish what AA doesn't" claim credibly. The hardcoded suite-v0 string will create user confusion immediately after the suite update. |
| **Recommendation** | Make suite/index versions dynamic (derive from the generated index). Build `WeightsTable` as a data-driven component (weights from a config, not hardcoded prose). Build `DiagnosticsPanel` once discrimination probe data exists. Update trust page to use actual badge components. |

---

### 1.8 Submission flow

| | Detail |
|---|---|
| **What exists** | Nothing. No `/submit` route exists in `web/app/`. The word "submit" does not appear in any page component. |
| **Missing / weak** | The entire contribution funnel is absent: no CLI instructions, no upload-manifest explainer, no tier/lane rules for submission, no ReplicatedBadge path explainer. There is no CTa on the home page or model pages pointing users to a submit flow. |
| **Severity** | High — without a submission path the site is read-only and cannot grow its dataset. This is the community-run acquisition funnel. |
| **Recommendation** | Build `/submit` as a static page (no server logic needed at launch) with: (1) copyable CLI command block, (2) what uploads vs what stays local, (3) tier/lane rules, (4) replicated path. This is a pure content page — low build cost. |

---

### 1.9 Axis-flexibility problem (the hardcoded-3-axes issue)

This is the most technically consequential gap. The v0 3-axis set (`mmlu_pro`, `ifeval`, `genmath`) is hardcoded in **5 distinct locations**, each requiring coordinated changes to generalize:

| Location | Hardcoding | Change required |
|---|---|---|
| `lib/schemas.ts` line 3 | `AXES = ["mmlu_pro", "ifeval", "genmath"] as const` | Replace with a dynamic axis registry driven by the data |
| `lib/schemas.ts` lines 30–34 | `AxesSchema = z.object({ mmlu_pro, ifeval, genmath })` | Replace with `z.record(z.string(), AxisScoreSchema)` or a parameterized schema |
| `lib/schemas.ts` line 78–82 | `SamplingSchema.by_bench` lists the 3 axes explicitly | Use `z.record()` |
| `lib/schemas.ts` line 174 | `worst_axis: bench: AxisSchema` — `AxisSchema = z.enum(AXES)` | Must become a string with runtime validation |
| `components/home-leaderboard.tsx` line 10 | `TABLE_AXES = ["mmlu_pro", "ifeval", "genmath"] as const` | Derive from the data's axis set |
| `components/home-leaderboard.tsx` lines 12–21 | `SortKey` type union hardcodes the 3 axis names | Must become a dynamic string-keyed sort |
| `components/home-leaderboard.tsx` lines 182–186 | `compareRows` switch has explicit `case "mmlu_pro": case "ifeval": case "genmath":` | Must be generalized |
| `lib/format.ts` lines 74–85 | `axisLabel()` switch enumerates all 3 axes with `assertNever` default | Must accept arbitrary string keys or be replaced with a lookup map |
| `app/run/[runId]/page.tsx` line 133 | `formatSampling` loops `AXES` to build sampling text | Must use axes from the data |
| `web/build_data.py` lines 19–20 | `BENCHES = ("genmath", "ifeval", "mmlu_pro")`, `WEIGHTS = {...}` | Must become configurable (JSON config or CLI argument) |
| `web/build_data.py` lines 74–85 | `_axes()` iterates `BENCHES` | Will automatically generalize once `BENCHES` is configurable |

**Quantifying the refactor:** The schema change is the critical path. `AxesSchema` is imported and used in `IndexModelSchema`, `ModelRunSchema`, `RunDetailSchema` — changing it from a fixed object to a `z.record()` changes the TypeScript type for `model.axes[axis]` everywhere. This breaks the TypeScript type safety for axis indexing (can no longer index with a typed `Axis` key) unless a type-narrowing helper is introduced. The `SortKey` union type in `home-leaderboard.tsx` is a branded literal union — making it dynamic requires converting the sort logic from a compile-time exhaustive switch to a runtime lookup, eliminating the `assertNever` guard.

**Estimated effort:** ~2 hours for a focused implementer who understands the codebase. It is a contained refactor — not a rebuild — but it touches every file in the data path and requires running the full test suite afterward. The axis-agnostic `assertNever` in `format.ts`'s `axisLabel()` will need replacement with a config-driven label map.

**The practical blocker:** The `AxesSchema` change from `z.object({...})` to `z.record()` loses compile-time axis validation. The recommended approach is to keep a `DOMAIN_AXES` constant in a new `lib/axis-config.ts` file that lists valid domain keys and their display labels — this becomes the single source of truth replacing the scattered hardcodes, while still allowing runtime validation.

---

### 1.10 Responsiveness, performance, accessibility, and tech-debt

| | Detail |
|---|---|
| **What exists** | Next.js 16 static export (fully static, no server). Tailwind responsive prefixes used in some places (`lg:grid-cols-[1fr_420px]`, `lg:px-8`, `sm:grid-cols-2`). SVG has `role="img"` + `aria-label`. Sort buttons use `<button type="button">` (not plain `<div>`). Zod validation on all JSON reads. Good test coverage for data access (vitest unit + Playwright e2e). |
| **Missing / weak** | **SVG charts are fixed-width** (`WIDTH=900`, `min-w-[760px]`) — they do not reflow at all on narrow screens, only scrolling horizontally. The scatter is not fluid/responsive. No `viewBox` scaling behavior that would let SVG scale down naturally; the fixed `min-w` forces a horizontal scroll container. The `home-leaderboard` table has `min-w-[1120px]` — valid for a data table, but no column-priority hiding at mobile breakpoints. **No skip-to-content link** for keyboard navigation. **No `<html lang>` fallback** — `layout.tsx` has `lang="en"` but no locale routing. The `body` uses only `className="font-sans antialiased"` — no `bg-bench-bg` class (background is set via raw CSS in `globals.css`, not via Tailwind, which is fine but inconsistent). The `font-sans` references `Aptos` as first choice — a Windows-only font that falls back to `Segoe UI Variable` on Windows 11 but to generic `system-ui` everywhere else (macOS/Linux users will see a different font). No web font loading (no `next/font` with Inter/JetBrains Mono as the spec recommends). The methodology page hardcodes `suite-v0 methodology` as a static string (will be wrong). **Dead code:** `lib/data.ts` re-exports `AXES` from `schemas.ts` (line 95) and this re-export propagates the hardcoded 3-axis list into the run-detail sampling formatter. |
| **Severity** | Medium (responsiveness/font), Low (dead-code), High (no web fonts — the spec requires tabular figures for number alignment, which system monospace may not provide on all platforms). |
| **Recommendation** | Add `next/font` with Inter + JetBrains Mono (or Geist Mono) loaded via `layout.tsx`. Make SVG charts use `width="100%"` with a `viewBox` and let the container control width. Add skip-to-content link. |

---

## 2. Top-10 prioritized gap list

Ranked by "highest leverage toward a shippable, differentiated product":

| # | Gap | Severity | Files affected | Estimated effort |
|---|---|---|---|---|
| 1 | **Axis-flexibility refactor** — replace hardcoded 3-axis set with a dynamic axis registry | Critical | `lib/schemas.ts`, `lib/format.ts`, `components/home-leaderboard.tsx`, `app/run/[runId]/page.tsx`, `web/build_data.py` + all test fixtures | ~2 hrs focused |
| 2 | **QuantDeltaStrip** — the launch-differentiator chart (quant-degradation paired-delta hero) is entirely absent | Critical | New component `components/quant-delta-strip.tsx`; requires schema additions (paired-delta records), model-page layout changes | ~1 day |
| 3 | **Home hero scatter absent** — QualityVsVramScatter must sit above the table as the landing hero; currently home opens directly to the table | Critical | `app/page.tsx` (layout), `components/model-scatter.tsx` (generalize to home context) + add VRAM-tier guide verticals, log toggle, lane control | ~4 hrs |
| 4 | **Missing token layer** — 14 semantic tokens absent from `tailwind.config.ts`; verdict/state colors needed for every new component | High | `tailwind.config.ts`, `app/globals.css`, refactor SVG hex literals | ~1 hr |
| 5 | **No persistent AppShell/TopNav** — trust and methodology pages are unreachable from model/run pages; no global nav | High | `app/layout.tsx` (add AppShell), all page components | ~2 hrs |
| 6 | **`/submit` page absent** — the entire community contribution funnel is missing | High | New `app/submit/page.tsx` (static content only) | ~2 hrs |
| 7 | **DiagnosticsPanel + WeightsTable absent from methodology** — the "we publish what AA doesn't" credibility moat has no UI expression | High | New `components/diagnostics-panel.tsx`, new `components/weights-table.tsx`, `app/methodology/page.tsx` refactor; requires diagnostics data schema | ~4 hrs (after data schema) |
| 8 | **Stale copy throughout** — home description hardcodes old axis names; methodology hardcodes `suite-v0`; no `index_version` anywhere | High | `app/page.tsx`, `app/methodology/page.tsx`, `lib/schemas.ts` (add `index_version`), `build_data.py` | ~1 hr |
| 9 | **No web fonts** — system font stack (`Aptos`) renders differently across platforms; tabular figures for number alignment not guaranteed | Medium | `app/layout.tsx` (add `next/font`), `app/globals.css` | ~30 min |
| 10 | **SVG charts not responsive** — fixed `WIDTH=900` with horizontal scroll only; no fluid reflow | Medium | `components/model-scatter.tsx`, `components/run-axis-breakdown.tsx` | ~2 hrs |

---

## 3. Detailed reference findings (AA comparison)

AA's landing page leads with a scatter (intelligence vs. cost) as its primary hero visualization, which confirms the spec's design direction is well-calibrated. Key differences where local-bench should diverge:

1. **AA's x-axis is API cost; local-bench's must be VRAM/footprint** — this is the correct axis swap for the local-user audience and is already specified. Not yet implemented.
2. **AA shows CIs only on its Arena Elo, not its Intelligence Index scatter** (confirmed by the fetch). local-bench's spec mandating CIs on every point is a genuine differentiation — but the current implementation only shows CIs in the table (as text), not visually on the scatter points. The scatter CI whiskers exist but only on the model page, not the home hero.
3. **AA has a filter/toggle UX** (provider, reasoning/non-reasoning). local-bench's FilterBar spec is more complete (VRAM budget slider, tier filter) but entirely absent from the current implementation.

---

## 4. Verdict

**The current front-end is a solid but narrow prototype, not a launch-ready product.** The code quality is high (TypeScript strict, Zod validation, good test coverage, clean component boundaries, correct CI math), and the shipped pieces (axis breakdown, scatter, table, badges, manifest card) are well-built and reusable. The dark palette tokens and the hand-rolled SVG approach are the right foundation.

However, three things make the current state pre-launch:

1. **The product's differentiator does not exist.** The QuantDeltaStrip — the chart that makes local-bench distinct from every other leaderboard — has no implementation and no data schema to feed it.
2. **The home page does not lead with the wedge.** A user landing on the site sees a table, not the VRAM scatter that tells the local-setup story. This is the single biggest first-impression gap.
3. **The axis hardcoding is a hard blocker for suite-v1.** The 3-axis set is woven into 10+ locations including the TypeScript type system; shipping new benchmark domains requires this refactor first.

**Verdict: extend, not rebuild.** The existing code is a strong base. The axis-flexibility refactor is a 2-hour surgery, not a rewrite. The missing components (QuantDeltaStrip, FilterBar, AppShell, Submit page) are additive, not replacements. The single biggest decision for the orchestrator is sequencing: the axis refactor must ship first (it breaks everything downstream), followed by the home hero scatter, followed by QuantDeltaStrip.

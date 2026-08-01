# Local Bench Design System

## 1. Atmosphere & Identity

Local Bench feels like a quiet benchmark command center: dense, factual, and fast to scan without becoming sterile. The signature is neon-on-graphite instrumentation: cyan and magenta accents on restrained dark panels, where numbers stay primary and color explains state rather than decorating the page.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | bench.bg | #0a0d14 | #0a0d14 | Page background |
| Surface/panel | bench.panel | #11151f | #11151f | Tables, cards, sections |
| Surface/secondary | bench.panel-2 | #0c0f17 | #0c0f17 | Nested surfaces |
| Border/default | bench.line | #222a38 | #222a38 | Panel and row borders |
| Border/strong | bench.line-strong | #38455a | #38455a | Emphasized dividers |
| Text/primary | bench.text | #eef2fa | #eef2fa | Headings and data |
| Text/secondary | bench.muted | #aab4c6 | #aab4c6 | Labels and supporting copy |
| Text/tertiary | bench.muted-2 | #98a4ba | #98a4ba | Low-emphasis metadata |
| Accent/primary | bench.accent | #3fd0d4 | #3fd0d4 | Primary metric emphasis |
| Accent/anchor | bench.anchor | #ff5fa8 | #ff5fa8 | Anchor/reference emphasis |
| Status/success | bench.better | #36e0b0 | #36e0b0 | Better outcomes |
| Status/error | bench.worse | #ff5c6e | #ff5c6e | Worse outcomes |
| Status/warning | bench.warn | #ffb627 | #ffb627 | Warnings and pending action |
| Status/mixed | bench.mixed | #b388ff | #b388ff | Mixed or candidate states |

### Rules

- Use color to encode metric role, status, or interaction state.
- Keep panels dark and opaque so table density remains legible.
- Do not introduce raw colors outside Tailwind bench tokens unless this file is extended first.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| H1 | 36px | 600 | 1.2 | 0 | Model and page titles |
| H2 | 18px | 600 | 1.4 | 0 | Section titles |
| Body | 16px | 400 | 1.6 | 0 | Primary explanatory text |
| Body/sm | 14px | 400 | 1.5 | 0 | Table body and secondary copy |
| Caption | 12px | 500 | 1.4 | 0 | Metadata and compact labels |
| Overline | 11px | 600 | 1.3 | 0.04em | Uppercase table headings |

### Font Stack

- Primary: `var(--font-sans)`, `ui-sans-serif`, `system-ui`
- Mono: `var(--font-mono)`, `ui-monospace`, `SFMono-Regular`

### Rules

- Use mono for identifiers, numeric metrics, route IDs, and provenance.
- Keep table headings compact and uppercase.
- Avoid viewport-scaled type; table density must stay predictable.

## 4. Spacing & Layout

### Base Unit

All spacing derives from 4px.

| Token | Value | Usage |
|-------|-------|-------|
| space-1 | 4px | Inline gaps |
| space-2 | 8px | Tight stacks |
| space-3 | 12px | Table cell vertical rhythm |
| space-4 | 16px | Compact panel padding |
| space-5 | 20px | Page side padding |
| space-6 | 24px | Section gaps |
| space-8 | 32px | Major page gaps |

### Grid

- Max content width: 1320px for model pages, 1180px for run pages.
- Tables may exceed viewport width and use horizontal overflow.
- Breakpoints follow Tailwind defaults.

### Rules

- Data tables use fixed minimum widths rather than squeezing columns into unreadable wraps.
- Page sections are full-width within the content rail, not nested cards inside cards.

## 5. Components

### Benchmark Table

- Structure: section header, horizontally scrollable table, compact cells.
- Variants: leaderboard, best-variant summary, model variant board.
- Spacing: 12px cell padding, 16px section header padding.
- States: row hover uses a subtle white overlay.
- Accessibility: include captions for dense tables when the title alone is not enough.

### Metric Bar

- Structure: numeric value, confidence interval, thin horizontal fill.
- Variants: composite score and axis mini bar.
- States: missing values render neutral text, not warning colors.
- Accessibility: preserve visible numbers; bars are supporting context only.

### Execution Profile Badge

- Structure: a prominent text-bearing `32k` or `8k` operating-point badge followed by a naturally wrapping human-readable budget summary; expose the exact profile ID in both title and accessible text.
- 32k state: cyan accent border/surface tokens; reserved for complete `generic_think_tags_32768_v1` and `gemma4_channel_32768_v1` v2 identities.
- 8k state: mixed-status border/surface tokens; applies to all earlier valid profiles, including rich v1 and id-only historical rows. The label denotes the historical operating point, never invalidity or supersession.
- Content: summarize static reasoning, final-answer, and server-context budgets when present; id-only profiles use their known reasoning mode. Keep template hashes and renderer internals in structured row data.
- Accessibility: state and summary remain explicit text at 200% zoom and never depend on color or hover.

### Operating Point View Toggle

- Configuration: `BOARD_DEFAULT_OPERATING_POINT_VIEW` accepts `mixed` or `32k-default`; `mixed` ships now and switching the literal to `32k-default` is the later one-line rollout.
- Structure: a compact board navigation strip above filters with links for the combined `8k + 32k` view, the `32k` view, and the exact archived label `archived operating point (2026-07, 8k)`.
- Deep links: the selected view is encoded in the stable `operating-point` query parameter. The archived value remains permanent so every preserved 8k row stays reachable after the default flips.
- 32k-default state: only 32k rows render until the archived link is followed; the archived view contains every non-32k historical row, including rows without a structured profile.
- Accessibility: the active link uses `aria-current="page"`; all state labels remain visible text and the strip wraps without horizontal overflow.

### Operating Point Notice

- Structure: a semantic `role="status"` notice inside the board container, before filters and table content.
- Gate: in `mixed`, render only when at least one board row carries a complete 32k profile. In `32k-default`, render the explanation only inside the archived view; other views render no placeholder.
- Tone: warning border/surface tokens with primary text for the owner-pinned compute-mismatch copy.
- Responsive behavior: wrap naturally at 375, 768, and 1280px without fixed dimensions or horizontal page overflow.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 100-150ms | ease-out | Hover and focus feedback |
| Standard | 200-300ms | ease-in-out | Panel or tab transitions |

### Rules

- Animate only color, opacity, and transform.
- Every clickable table/link element keeps hover and focus affordance.

## 7. Depth & Surface

### Strategy

Mixed: borders define dense table structure; tonal shifts separate panels. Shadows are reserved for the main leaderboard container only.

| Type | Token | Usage |
|------|-------|-------|
| Border/default | bench.line | Table rows, cards, panels |
| Surface/default | bench.panel | Main panels |
| Surface/nested | bench.panel-2 | Secondary panels |

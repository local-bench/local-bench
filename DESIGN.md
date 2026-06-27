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

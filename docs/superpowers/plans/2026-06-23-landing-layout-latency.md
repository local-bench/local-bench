# Landing Layout Re-org + Time-to-Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the graph + summary board to the top of the landing page, move the full detailed leaderboard to a new `/leaderboard` page, and add a per-answer "Time/answer" latency column to both boards (with total run time surfaced on the run-detail page).

**Architecture:** Latency is computed once at build time (`latency_s_median = tokens_to_answer_median ÷ tok/s`) and emitted onto each measured model/run row, then plumbed to both boards through the existing data types. The landing page is re-ordered and the detailed leaderboard relocates to its own route; nav gains a "Full board" link. No scoring/axes/composite logic changes.

**Tech Stack:** Next.js 16 (app router, static export), React 19, TypeScript, Zod, Tailwind, Vitest (unit), Playwright (e2e), Python 3.14 (`build_data.py`).

## Global Constraints

- **Methodology v1.2 is untouched** — no changes to scoring, axes, weights, or composite. The only new data field is `latency_s_median`.
- **Latency definition:** `tokens_to_answer_median ÷ tok/s`, in seconds; `None`/`null` when either input is missing or `tok/s ≤ 0`. It is a test-rig estimate (includes thinking tokens) — UI labels it as a guide.
- **Null display convention for latency:** render `—` (em dash) for absent latency.
- **Build data with the pinned venv:** `cli/.venv/Scripts/python.exe web/build_data.py` (run from repo root `<home>\local-bench`).
- **Web commands run in `web/`:** `npm run typecheck`, `npm run test`, `npm run build`.
- **Commits stay local, never pushed.** Per the repo's "commit only when asked" rule, treat the per-task commit steps as checkpoints — confirm with the user before committing, or batch to the end.
- Follow existing component/format patterns. The codebase unit-tests lib logic (not TSX); UI is verified by typecheck + `next build` + grepping the static export under `web/out/`.

---

### Task 1: `formatLatencySeconds` formatter

**Files:**
- Modify: `web/lib/format.ts` (add one exported function near `formatSeconds`)
- Test: `web/tests/format.test.ts` (new)

**Interfaces:**
- Produces: `formatLatencySeconds(value: number | null | undefined): string` → `"~13 s"` (<90s), `"~2.2 min"` (≥90s), `"—"` (null/undefined).

- [ ] **Step 1: Write the failing test**

Create `web/tests/format.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { formatLatencySeconds } from "../lib/format";

describe("formatLatencySeconds", () => {
  it("formats sub-90s values as whole seconds with a tilde", () => {
    expect(formatLatencySeconds(13.4)).toBe("~13 s");
  });
  it("rolls up to minutes at or above 90s", () => {
    expect(formatLatencySeconds(132)).toBe("~2.2 min");
  });
  it("renders an em dash for null/undefined", () => {
    expect(formatLatencySeconds(null)).toBe("—");
    expect(formatLatencySeconds(undefined)).toBe("—");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `web/`): `npm run test -- format`
Expected: FAIL — `formatLatencySeconds` is not exported.

- [ ] **Step 3: Add the implementation**

In `web/lib/format.ts`, add after `formatSeconds` (the function ending at the `formatSeconds` return):
```ts
export function formatLatencySeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (value >= 90) {
    return `~${COMPACT_FORMAT.format(value / 60)} min`;
  }
  return `~${INTEGER_FORMAT.format(value)} s`;
}
```
(`COMPACT_FORMAT` and `INTEGER_FORMAT` already exist at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run (in `web/`): `npm run test -- format`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/lib/format.ts web/tests/format.test.ts
git commit -m "feat(web): add formatLatencySeconds for per-answer latency"
```

---

### Task 2: Emit `latency_s_median` at build time

**Files:**
- Modify: `web/build_data.py` (`_build_run`, the `model_row` and `index_row` dict literals)
- Modify: `web/lib/schemas.ts` (`IndexModelSchema`, `ModelRunSchema`)
- Test: `web/tests/data.test.ts` (add one `it` block)

**Interfaces:**
- Produces: `latency_s_median: number | null` on every measured `model_row` and `index_row`; absent (→ `undefined`) on catalog shells and demo rows. Surfaced on `IndexModel` and `ModelRun` types as `latency_s_median?: number | null`.

- [ ] **Step 1: Write the failing test**

In `web/tests/data.test.ts`, add `getModelData` to the import from `../lib/data`, then add inside the `describe("static data access", ...)` block:
```ts
  it("emits per-answer latency for measured runs", async () => {
    const model = await getModelData("qwen3-6-27b");
    const measured = model.runs.find((run) => run.run_id !== null && run.composite !== null);
    expect(measured).toBeDefined();
    expect(typeof measured?.latency_s_median).toBe("number");
    expect(measured?.latency_s_median ?? 0).toBeGreaterThan(0);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `web/`): `npm run test -- data`
Expected: FAIL — `latency_s_median` is `undefined` (field not emitted yet).

- [ ] **Step 3: Add the schema fields**

In `web/lib/schemas.ts`, add to `IndexModelSchema` (e.g. after the `est_cost_usd` line):
```ts
  latency_s_median: z.number().nullable().optional(),
```
and add the identical line to `ModelRunSchema` (e.g. after its `tok_s` line).

- [ ] **Step 4: Compute and emit the field in the builder**

In `web/build_data.py`, inside `_build_run`, immediately before the `summary = _manifest_summary(...)` line, add:
```python
    tok_s = _number_or_none(totals.get("completion_tokens_per_second"))
    latency_s_median = round(tokens["median"] / tok_s, 3) if tokens["median"] is not None and tok_s and tok_s > 0 else None
```
In the `model_row` dict, replace `"tok_s": _number_or_none(totals.get("completion_tokens_per_second")),` with:
```python
        "tok_s": tok_s, "latency_s_median": latency_s_median,
```
In the `index_row` dict, add (e.g. after `"est_cost_usd": est_cost,`):
```python
        "latency_s_median": latency_s_median,
```

- [ ] **Step 5: Rebuild the static data**

Run (from repo root): `cli/.venv/Scripts/python.exe web/build_data.py`
Expected: prints `wrote web\public\data`, exit 0.

- [ ] **Step 6: Run test to verify it passes**

Run (in `web/`): `npm run test -- data`
Expected: PASS. Also run `npm run typecheck` → exit 0.

- [ ] **Step 7: Commit**

```bash
git add web/build_data.py web/lib/schemas.ts web/tests/data.test.ts web/public/data
git commit -m "feat(web): emit per-answer latency_s_median in build_data"
```

---

### Task 3: Plumb latency to best-variant points

**Files:**
- Modify: `web/lib/rig-match.ts` (`RigMatchCandidate` type)
- Modify: `web/lib/data.ts` (`toRigMatchCandidate`)
- Modify: `web/lib/best-variant.ts` (`BestVariantPoint` type + `selectBestVariantPoints` point literal)
- Test: `web/tests/best-variant.test.ts` (new)

**Interfaces:**
- Consumes: `ModelRun.latency_s_median` (Task 2).
- Produces: `RigMatchCandidate.latencySMedian: number | null` and `BestVariantPoint.latencySMedian: number | null`.

- [ ] **Step 1: Write the failing test**

Create `web/tests/best-variant.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { selectBestVariantPoints } from "../lib/best-variant";
import type { RigMatchCandidate } from "../lib/rig-match";

function candidate(overrides: Partial<RigMatchCandidate> = {}): RigMatchCandidate {
  return {
    axes: {},
    demo: false,
    family: "Qwen3.6",
    kind: "community",
    lane: "capped-thinking",
    modelLabel: "Qwen3.6-27B",
    modelSlug: "qwen3-6-27b",
    nItems: 694,
    nRuns: 5,
    quantLabel: "Q4_K_M",
    runId: "qwen3-6-27b__ladder-q4",
    score: { point: 74.9, lo: 72, hi: 77 },
    scoreStatus: "measured",
    tier: "standard",
    tokS: 140,
    vramFootprintGb: 16.55,
    vramRequiredGb8k: 18.7,
    latencySMedian: 13.2,
    ...overrides,
  };
}

describe("selectBestVariantPoints", () => {
  it("carries per-answer latency onto the best-variant point", () => {
    const points = selectBestVariantPoints([candidate()]);
    expect(points).toHaveLength(1);
    expect(points[0].latencySMedian).toBe(13.2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `web/`): `npm run test -- best-variant`
Expected: FAIL — `latencySMedian` missing on `RigMatchCandidate`/`BestVariantPoint` (type + value error).

- [ ] **Step 3: Add the field to the types and carry it through**

In `web/lib/rig-match.ts`, add to the `RigMatchCandidate` type (after `tokS`):
```ts
  readonly latencySMedian: number | null;
```
In `web/lib/data.ts`, in `toRigMatchCandidate`, add (after `tokS: run.tok_s,`):
```ts
    latencySMedian: run.latency_s_median ?? null,
```
In `web/lib/best-variant.ts`, add to the `BestVariantPoint` type (after `tokS`):
```ts
  readonly latencySMedian: number | null;
```
and in `selectBestVariantPoints`, in the `point` object literal (after `tokS: candidate.tokS,`):
```ts
      latencySMedian: candidate.latencySMedian,
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `web/`): `npm run test -- best-variant` → PASS. Then `npm run typecheck` → exit 0 (confirms every `RigMatchCandidate` construction supplies the new field).

- [ ] **Step 5: Commit**

```bash
git add web/lib/rig-match.ts web/lib/data.ts web/lib/best-variant.ts web/tests/best-variant.test.ts
git commit -m "feat(web): plumb per-answer latency to best-variant points"
```

---

### Task 4: Add "Time/answer" column to the summary board

**Files:**
- Modify: `web/components/best-variant-table.tsx`

**Interfaces:**
- Consumes: `BestVariantPoint.latencySMedian` (Task 3), `formatLatencySeconds` (Task 1).

- [ ] **Step 1: Add the column**

In `web/components/best-variant-table.tsx`:
- Update the format import to include `formatLatencySeconds`:
```ts
import { formatCi, formatCompactNumber, formatGb, formatLatencySeconds, formatScore } from "@/lib/format";
```
- In `<thead>`, after `<th className="px-3 py-3">tok/s</th>`, add:
```tsx
            <th className="px-3 py-3">Time/answer</th>
```
- In `<tbody>`, after the tok/s cell `<td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(point.tokS)}</td>`, add:
```tsx
                <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(point.latencySMedian)}</td>
```

- [ ] **Step 2: Typecheck + build**

Run (in `web/`): `npm run typecheck` (exit 0), then `npm run build` (exit 0).

- [ ] **Step 3: Verify in the static export**

Run (in `web/`): `grep -c "Time/answer" out/index.html`
Expected: ≥ 1 (the summary board on the landing page now has the column header).

- [ ] **Step 4: Commit**

```bash
git add web/components/best-variant-table.tsx
git commit -m "feat(web): add Time/answer column to the summary board"
```

---

### Task 5: New `/leaderboard` page + landing re-order + nav

**Files:**
- Create: `web/app/leaderboard/page.tsx`
- Modify: `web/app/page.tsx` (re-order; remove the full-leaderboard section)
- Modify: `web/components/app-shell.tsx` (add "Full board" nav link)
- Modify: `web/e2e/data.ts` (add `/leaderboard` to `getAllStaticRoutes`)

**Interfaces:**
- Consumes: `getIndexData`, `getHomePageData`, `selectBestVariantPoints`, `HomeLeaderboard`.

- [ ] **Step 1: Create the leaderboard page**

Create `web/app/leaderboard/page.tsx`:
```tsx
import { HomeLeaderboard } from "@/components/home-leaderboard";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getIndexData } from "@/lib/data";

export default async function LeaderboardPage() {
  const index = await getIndexData();
  const axisNames = AXIS_CONFIG.filter((axis) => index.models.some((model) => model.axes[axis.key] !== undefined)).map(
    (axis) => axis.label,
  );
  const hasMeasuredRankedData = index.models.some(
    (model) => model.score_status === "measured" && model.ranked && !model.demo && model.composite !== null,
  );
  const suiteLabel = index.suite_version ?? "scoreless catalog";
  const axisCopy = hasMeasuredRankedData
    ? `Every ranked model is scored on the same frozen suite${axisNames.length > 0 ? ` across ${axisNames.join(", ")}` : ""}. This is the initial measured ladder — more models land as runs are submitted.`
    : "Catalog models are listed as score-less shells until benchmark runs land.";

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <section className="flex flex-col gap-4">
        <div className="grid gap-5 border-b border-bench-line pb-5 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase text-bench-accent">
              {suiteLabel} / {index.index_version}
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-bench-text">Full leaderboard</h2>
            <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
              {axisCopy} The {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) appears only
              after a measured run attaches to a catalog model and quant. {LOCAL_INTELLIGENCE_INDEX_PROFILE}.
            </p>
          </div>
          <div className="rounded-lg border border-bench-warn/35 bg-bench-warn/[0.08] p-4 text-sm leading-6 text-bench-warn-soft">
            <strong className="text-bench-warn">Quick tier = personal estimate, UNRANKED.</strong> Standard tier is
            the only ranked board, and ranks are only within the same reasoning lane. Rows are sorted for browsing
            only; reasoning lanes are not directly comparable.
          </div>
        </div>
        <HomeLeaderboard models={index.models} />
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Re-order the landing page and remove the full board**

Replace the entire contents of `web/app/page.tsx` with:
```tsx
import Link from "next/link";
import { RigMatchFinder } from "@/components/rig-match-finder";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { getHomePageData } from "@/lib/data";
import { selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, rigAnchors, rigCandidates } = await getHomePageData();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates);

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
      <BestVariantTable points={bestVariantPoints} />
      <RigMatchFinder anchors={rigAnchors} candidates={rigCandidates} />
      <Link
        href="/leaderboard"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View full leaderboard →
      </Link>
    </main>
  );
}
```

- [ ] **Step 3: Add the nav link**

In `web/components/app-shell.tsx`, after the `Leaderboard` `<Link href="/">` block, add:
```tsx
              <Link href="/leaderboard" className="hover:text-bench-text">
                Full board
              </Link>
```

- [ ] **Step 4: Register the route for e2e route coverage**

In `web/e2e/data.ts`, in `getAllStaticRoutes`, add to `contentRoutes` after the `/` entry:
```ts
    { path: "/leaderboard", screenshotName: "route-leaderboard" },
```

- [ ] **Step 5: Typecheck + build**

Run (in `web/`): `npm run typecheck` (exit 0), then `npm run build` (exit 0). Build output must list a `/leaderboard` route.

- [ ] **Step 6: Verify the split in the static export**

Run (in `web/`):
```bash
test -f out/leaderboard/index.html && grep -c "full-leaderboard" out/leaderboard/index.html   # expect >=1
grep -c "full-leaderboard" out/index.html                                                     # expect 0
grep -o "best-variant-scatter\|rig-match-finder" out/index.html | head -2                      # expect scatter first
grep -c "Full board" out/index.html                                                            # expect >=1 (nav)
grep -c "View full leaderboard" out/index.html                                                 # expect >=1 (CTA)
```

- [ ] **Step 7: Commit**

```bash
git add web/app/leaderboard/page.tsx web/app/page.tsx web/components/app-shell.tsx web/e2e/data.ts
git commit -m "feat(web): move detailed leaderboard to /leaderboard; lead landing with graph + summary"
```

---

### Task 6: Add sortable "Time/answer" column to the detailed board

**Files:**
- Modify: `web/components/home-leaderboard.tsx`

**Interfaces:**
- Consumes: `IndexModel.latency_s_median` (Task 2), `formatLatencySeconds` (Task 1).

- [ ] **Step 1: Add the column (header, cell, sort case)**

In `web/components/home-leaderboard.tsx`:
- Add `formatLatencySeconds` to the format import:
```ts
import { axisLabel, formatCost, formatInteger, formatLatencySeconds } from "@/lib/format";
```
- In `<thead>`, between the `Tokens` and `Cost` `SortableHeader`s, add:
```tsx
            <SortableHeader label="Time/answer" sortKey="latency" sort={sort} onSort={setSort} />
```
- In `<tbody>`, after the Tokens cell (`<td className="px-3 py-3 font-mono text-bench-text">{formatInteger(model.tokens_to_answer_median)}</td>`), add:
```tsx
              <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(model.latency_s_median ?? null)}</td>
```
- In `compareRows`, add a case before `default:`:
```ts
    case "latency":
      return nullableNumber(left.latency_s_median ?? null) - nullableNumber(right.latency_s_median ?? null);
```

- [ ] **Step 2: Typecheck + build**

Run (in `web/`): `npm run typecheck` (exit 0), then `npm run build` (exit 0).

- [ ] **Step 3: Verify in the static export**

Run (in `web/`): `grep -c "Time/answer" out/leaderboard/index.html`
Expected: ≥ 1.

- [ ] **Step 4: Commit**

```bash
git add web/components/home-leaderboard.tsx
git commit -m "feat(web): add sortable Time/answer column to the detailed leaderboard"
```

---

### Task 7: Surface total run time on the run-detail page

**Files:**
- Modify: `web/app/run/[runId]/page.tsx`

**Interfaces:**
- Consumes: `run.totals.wall_time_seconds`, `formatSeconds` (already imported).

- [ ] **Step 1: Add a header stat + relabel the manifest row**

In `web/app/run/[runId]/page.tsx`:
- In the header `<div className="mt-5 flex flex-wrap items-end gap-4">`, after the closing `</div>` of the axis-profile block (the one rendering `CoreTextAxisProfile`), add a new stat:
```tsx
          <div className="pb-2 text-sm text-bench-muted">
            <div className="font-mono text-xs uppercase text-bench-muted">Total run time</div>
            <div className="mt-1 font-mono text-lg text-bench-text">{formatSeconds(run.totals.wall_time_seconds)}</div>
          </div>
```
- In `ManifestCard`, relabel the wall-time row: change `<DetailItem label="wall-time" value={formatSeconds(run.totals.wall_time_seconds)} />` to `label="total run time"`.

- [ ] **Step 2: Build**

Run (in `web/`): `npm run build` (exit 0).

- [ ] **Step 3: Verify in the static export**

Run (in `web/`): `grep -c "Total run time" out/run/qwen3-6-27b__ladder-qwen36-27b-Q4_K_M/index.html`
Expected: ≥ 1.

- [ ] **Step 4: Commit**

```bash
git add "web/app/run/[runId]/page.tsx"
git commit -m "feat(web): surface total run time on the run-detail header"
```

---

### Task 8: Update layout-affected e2e specs (data-agnostic)

> **Scope note:** The e2e suite has **pre-existing data staleness** from the 27B wiring (specs in `run-detail.spec.ts`, `model.spec.ts`, `content.spec.ts`, and parts of `home.spec.ts` reference demo / `lcpp` / Qwen3-32B rows that no longer exist). A full e2e refresh is OUT OF SCOPE for this layout change and tracked separately. This task only updates the assertions that describe the **layout we are changing**, written data-agnostically (structure/testids, not model names), so they hold after the separate data refresh.

**Files:**
- Modify: `web/e2e/home.spec.ts` (rewrite the hero-order test; remove the on-`/` leaderboard test)
- Create: `web/e2e/leaderboard.spec.ts`

- [ ] **Step 1: Rewrite the home hero test**

In `web/e2e/home.spec.ts`, replace the `test("renders the rig-match finder as the home hero", ...)` body with a structural, data-agnostic version:
```ts
test("leads with the graph + summary board, finder below", async ({ page }) => {
  await visitRoute(page, "/");

  await expect(page.getByTestId("best-variant-scatter")).toBeVisible();
  await expect(page.getByTestId("best-variant-table")).toBeVisible();
  await expect(page.getByTestId("rig-match-finder")).toBeVisible();
  await expect(page.getByTestId("full-leaderboard")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /View full leaderboard/i })).toBeVisible();

  const scatterBox = await page.getByTestId("best-variant-scatter").boundingBox();
  const finderBox = await page.getByTestId("rig-match-finder").boundingBox();
  expect(scatterBox).not.toBeNull();
  expect(finderBox).not.toBeNull();
  expect(finderBox?.y ?? 0).toBeGreaterThan(scatterBox?.y ?? 0);
});
```

- [ ] **Step 2: Remove the obsolete on-`/` leaderboard test**

In `web/e2e/home.spec.ts`, delete the entire `test("renders the leaderboard and keeps index sorting deterministic", ...)` block (its behaviour moves to `leaderboard.spec.ts`). Remove the now-unused `readIndexData` import if nothing else uses it.

- [ ] **Step 3: Create the leaderboard spec**

Create `web/e2e/leaderboard.spec.ts`:
```ts
import { expect, test, visitRoute } from "./fixtures";

test("renders the full detailed leaderboard with a Time/answer column", async ({ page }) => {
  await visitRoute(page, "/leaderboard");

  await expect(page.getByRole("heading", { name: "Full leaderboard" })).toBeVisible();
  const leaderboard = page.getByTestId("full-leaderboard");
  await expect(leaderboard).toBeVisible();
  await expect(leaderboard.getByRole("button", { name: "Time/answer" })).toBeVisible();
  await expect(page.getByText(/reasoning lanes are not directly comparable/i)).toBeVisible();
});
```

- [ ] **Step 4: Typecheck the specs**

Run (in `web/`): `npm run typecheck` (exit 0 — confirms the specs compile against the harness).

> Running the full Playwright suite (`npm run e2e`) is gated on the separate e2e data refresh and is not a checkpoint for this plan.

- [ ] **Step 5: Commit**

```bash
git add web/e2e/home.spec.ts web/e2e/leaderboard.spec.ts
git commit -m "test(web): update layout e2e specs for graph-first landing + /leaderboard"
```

---

## Final verification

- [ ] In `web/`: `npm run test` → all unit suites PASS.
- [ ] In `web/`: `npm run typecheck` → exit 0.
- [ ] From repo root: `cli/.venv/Scripts/python.exe web/build_data.py` then in `web/`: `npm run build` → exit 0, with `/leaderboard` listed.
- [ ] Static-export spot checks pass: `out/index.html` (graph→summary→finder, "Time/answer", CTA, no `full-leaderboard`), `out/leaderboard/index.html` (`full-leaderboard`, "Time/answer"), `out/run/.../index.html` ("Total run time").

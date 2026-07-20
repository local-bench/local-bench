import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BoardIndexChart } from "../components/board-index-chart";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import { IndexModelSchema, type AxisScore, type IndexModel, type Score } from "../lib/schemas";

const PLOT_TOP = 32;
const PLOT_HEIGHT = 240;
const SLOT_WIDTH = 88;
const PLOT_LEFT = 42;
const PLOT_RIGHT = 18;

function score(point: number, lo = point - 3, hi = point + 3): Score {
  return { hi, lo, point };
}

function axis(point: number): AxisScore {
  return {
    hi: point,
    lo: point,
    n: 10,
    n_errors: 0,
    n_no_answer: 0,
    point,
    raw_accuracy: point / 100,
  };
}

function allAxes(point: number): Readonly<Record<string, AxisScore>> {
  return {
    agentic: axis(point),
    coding: axis(point),
    instruction: axis(point),
    knowledge: axis(point),
    math: axis(point),
    tool_calling: axis(point),
  };
}

function rankedModel(input: {
  readonly slug: string;
  readonly label?: string;
  readonly tier?: string | null;
  readonly composite?: Score | null;
  readonly compositeFull?: Score | null;
  readonly axes?: Readonly<Record<string, AxisScore>>;
}): IndexModel {
  return IndexModelSchema.parse({
    axes: input.axes ?? allAxes(input.compositeFull?.point ?? input.composite?.point ?? 50),
    best_run_id: `${input.slug}-run`,
    composite: input.composite === undefined ? score(50) : input.composite,
    composite_full: input.compositeFull,
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "community",
    lane: HEADLINE_LANE,
    model_label: input.label ?? input.slug,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: input.slug,
    tier: input.tier ?? "Q4_K_M",
    tokens_to_answer_median: 128,
  });
}

function render(models: readonly IndexModel[]): string {
  return renderToStaticMarkup(createElement(BoardIndexChart, { models }));
}

function linkedSlugs(html: string): readonly string[] {
  return Array.from(html.matchAll(/<a [^>]*href="\/model\/([^"]+)"/g), (match) => match[1] ?? "");
}

function attrValues(html: string, attribute: string): readonly string[] {
  const pattern = new RegExp(`${attribute}="([^"]+)"`, "g");
  return Array.from(html.matchAll(pattern), (match) => match[1] ?? "");
}

function yFor(value: number): number {
  return Number((PLOT_TOP + (1 - value / 100) * PLOT_HEIGHT).toFixed(3));
}

describe("BoardIndexChart", () => {
  it("renders nothing when the ranked board is empty", () => {
    expect(render([])).toBe("");
  });

  it("orders rows by full score and uses composite_full when composite is absent", () => {
    const html = render([
      rankedModel({ slug: "low", label: "Low", composite: score(20), compositeFull: null }),
      rankedModel({ slug: "fallback-high", label: "Fallback High", composite: null, compositeFull: score(70, 64, 78) }),
      rankedModel({ slug: "middle", label: "Middle", composite: score(55), compositeFull: null }),
    ]);

    expect(linkedSlugs(html)).toEqual(["fallback-high", "middle", "low"]);
    expect(html).toContain("70.0");
    expect(html).toContain("Fallback High");
  });

  it("draws one focusable model link per row", () => {
    const rows = [
      rankedModel({ slug: "alpha", label: "Alpha" }),
      rankedModel({ slug: "beta", label: "Beta" }),
      rankedModel({ slug: "gamma", label: "Gamma" }),
    ];
    const html = render(rows);

    expect(linkedSlugs(html)).toEqual(["alpha", "beta", "gamma"]);
    for (const row of rows) {
      expect(html.match(new RegExp(`href="/model/${row.slug}/"`, "g")) ?? []).toHaveLength(1);
    }
  });

  it("cues horizontal scrolling when ranked bars extend past the viewport", () => {
    const html = render([rankedModel({ slug: "scroll-cue", label: "Scroll Cue" })]);

    expect(html).toContain("Swipe horizontally to see all ranked bars");
  });

  it("puts the uncertainty range in the tooltip instead of drawing whiskers", () => {
    const html = render([rankedModel({ slug: "ci-row", composite: score(50, 20, 80) })]);

    // Whiskers are gone (owner call 2026-07-09); the uncertainty range lives in the tooltip.
    expect(html).not.toContain("data-whisker-y1=");
    expect(html).toContain("50.0 (20.0–80.0)");
  });

  it("clamps bar geometry to the one-hundred gridline", () => {
    const html = render([rankedModel({ slug: "too-high", composite: score(150, 120, 180) })]);

    expect(html).toContain(`data-bar-top="${PLOT_TOP}"`);
  });

  it("leaves partial axis rows uninflated and names missing axes in the tooltip", () => {
    const html = render([
      rankedModel({
        slug: "partial",
        composite: score(60),
        axes: {
          agentic: axis(50),
          coding: axis(40),
        },
      }),
    ]);

    // Solid bars carry the breakdown in the tooltip: measured contributions stay uninflated
    // and the gap is named, never painted into the measured numbers.
    expect(html).toContain("Agentic 20.0");
    expect(html).toContain("Coding 6.0");
    expect(html).toContain("Unallocated 34.0");
    expect(html).toContain("Missing: Knowledge, Instruction, Tool calling, Math");
  });

  it("renders the score bar and whisker without NaN geometry when contributions sum to zero", () => {
    const html = render([
      rankedModel({
        slug: "zero-stack",
        composite: score(45, 40, 50),
        axes: allAxes(-10),
      }),
    ]);

    expect(html).not.toContain("NaN");
    expect(html).toContain("45.0");
  });

  it("fills each bar with its family color", () => {
    const html = render([rankedModel({ slug: "family-row", label: "Family Row" })]);

    expect(html).toMatch(/data-bar-fill="#[0-9a-fA-F]{6}"/);
  });

  it.each([1, 3, 20, 40])("keeps bar and label centers aligned for %i row(s)", (count) => {
    const models = Array.from({ length: count }, (_, index) =>
      rankedModel({
        slug: `row-${index}`,
        label: `Row ${index}`,
        composite: score(100 - index),
      }),
    );
    const html = render(models);
    const expectedWidth = PLOT_LEFT + PLOT_RIGHT + count * SLOT_WIDTH;

    expect(html).toContain(`width:${expectedWidth}px`);
    expect(attrValues(html, "data-bar-center")).toEqual(attrValues(html, "data-label-center"));
  });

  it("renders the CSS-only tooltip and focus-within hooks", () => {
    const html = render([rankedModel({ slug: "tooltip-row", label: "Tooltip Row" })]);

    expect(html).toContain('data-tooltip-hit-target="tooltip-row"');
    expect(html).toContain("group-hover:opacity-100");
    expect(html).toContain("group-focus-within:opacity-100");
    expect(html).toContain('aria-hidden="true"');
  });
});

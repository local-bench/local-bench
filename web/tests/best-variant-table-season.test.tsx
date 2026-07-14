import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { BestVariantTable } from "../components/best-variant-table";
import type { BestVariantPoint } from "../lib/best-variant";
import type { AxisScore } from "../lib/schemas";

// The landing summary table must carry the SAME season identity as the leaderboard it
// summarizes: season-2 points (tool_use macro-axis present) get the index-v4.0 qualifier and
// the 20/24/24/24/8 axis columns; a v3-only board keeps the season-1 columns. Regression test
// for the 2026-07-15 landing/leaderboard mismatch (landing still showed "Index v3.0" +
// dead Agentic / Tool calling n/a columns after the season-2 cutover).

function axis(point: number): AxisScore {
  return {
    point,
    lo: point - 2,
    hi: point + 2,
    raw_accuracy: point / 100,
    n: 100,
    n_errors: 0,
    n_no_answer: 0,
  };
}

function fixturePoint(axes: Readonly<Record<string, AxisScore>>): BestVariantPoint {
  return {
    axes,
    effectiveVramGb: 20,
    family: "Fixture",
    isFrontier: false,
    modelLabel: "Fixture Model",
    modelSlug: "fixture-model",
    nRuns: 1,
    quantLabel: "Q4_K_M",
    runId: "fixture-model__q4km",
    score: { point: 55.5, lo: 52.7, hi: 58.3 },
    tokS: 100,
    latencySMedian: 5,
    wallTimeSeconds: 1000,
  };
}

const SEASON_2_AXES: Readonly<Record<string, AxisScore>> = {
  tool_use: axis(17.7),
  knowledge: axis(87.4),
  instruction: axis(79.3),
  coding: axis(33.8),
  math: axis(48.2),
};

const SEASON_1_AXES: Readonly<Record<string, AxisScore>> = {
  agentic: axis(2.0),
  knowledge: axis(70),
  instruction: axis(65),
  tool_calling: axis(60),
  coding: axis(40),
  math: axis(30),
};

describe("BestVariantTable season identity", () => {
  it("renders season-2 identity and axis columns for a v4 board", () => {
    const html = renderToStaticMarkup(
      createElement(BestVariantTable, { points: [fixturePoint(SEASON_2_AXES)] }),
    );
    expect(html).toContain("index-v4.0 | 20/24/24/24/8");
    expect(html).toContain("Tool use 20%");
    expect(html).toContain("Knowledge 24%");
    expect(html).toContain("Instruction 24%");
    expect(html).toContain("Coding 24%");
    expect(html).toContain("Math 8%");
    expect(html).not.toContain("index-v3.0");
    expect(html).not.toContain("Agentic");
    expect(html).not.toContain("Tool calling");
    // Every season-2 axis is measured in the fixture, so no dead n/a cells may render.
    expect(html).not.toContain("n/a");
  });

  it("keeps season-1 identity and axis columns for a v3-only board", () => {
    const html = renderToStaticMarkup(
      createElement(BestVariantTable, { points: [fixturePoint(SEASON_1_AXES)] }),
    );
    expect(html).toContain("index-v3.0 | 40/15/15/10/15/5");
    expect(html).toContain("Agentic 40%");
    expect(html).toContain("Knowledge 15%");
    expect(html).toContain("Instruction 15%");
    expect(html).toContain("Tool calling 10%");
    expect(html).toContain("Coding 15%");
    expect(html).toContain("Math 5%");
    expect(html).not.toContain("index-v4.0");
  });
});

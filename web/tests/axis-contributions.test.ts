import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { IndexContributionRail } from "../components/score-bar";
import {
  INDEX_AXIS_WEIGHTS,
  contributionTotal,
  indexContributionTitle,
  indexContributions,
} from "../lib/axis-contributions";
import type { AxisScore } from "../lib/schemas";

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

const FIXTURE_AXES = {
  agentic: axis(50),
  coding: axis(40),
  instruction: axis(10),
  knowledge: axis(20),
  math: axis(80),
  tool_calling: axis(30),
} satisfies Readonly<Record<string, AxisScore>>;

describe("indexContributions", () => {
  it("keeps the canonical index weights summing to one", () => {
    const sum = Object.values(INDEX_AXIS_WEIGHTS).reduce((total, weight) => total + weight, 0);

    expect(INDEX_AXIS_WEIGHTS).toEqual({
      agentic: 0.4,
      coding: 0.15,
      instruction: 0.15,
      knowledge: 0.15,
      math: 0.05,
      tool_calling: 0.1,
    });
    expect(sum).toBeCloseTo(1, 12);
  });

  it("computes weighted contributions in canonical display order", () => {
    const contributions = indexContributions(FIXTURE_AXES);

    expect(contributions.map((contribution) => contribution.key)).toEqual([
      "agentic",
      "knowledge",
      "instruction",
      "tool_calling",
      "coding",
      "math",
    ]);
    expect(contributions.map((contribution) => contribution.contribution)).toEqual([20, 3, 1.5, 3, 6, 4]);
    expect(contributionTotal(contributions)).toBe(37.5);
  });

  it("treats missing and invalid axis inputs as zero-height contributions", () => {
    const contributions = indexContributions({
      agentic: axis(Number.NaN),
      coding: axis(-30),
      knowledge: axis(20),
      tool_calling: axis(Number.POSITIVE_INFINITY),
    });

    expect(contributions.map((contribution) => contribution.contribution)).toEqual([0, 3, 0, 0, 0, 0]);
    expect(contributionTotal(contributions)).toBe(3);
  });

  it("preserves the historical IndexContributionRail title string byte-for-byte", () => {
    const historicalTitle =
      "Agentic 20.0 + Knowledge 3.0 + Instruction 1.5 + Tool 3.0 + Coding 6.0 + Math 4.0 = 37.5";

    const title = indexContributionTitle(indexContributions(FIXTURE_AXES));
    const html = renderToStaticMarkup(createElement(IndexContributionRail, { axes: FIXTURE_AXES }));

    expect(title).toBe(historicalTitle);
    expect(html).toContain(`title="${historicalTitle}"`);
  });
});

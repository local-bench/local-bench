import { describe, expect, it } from "vitest";
import { splitLeaderboard } from "../lib/leaderboard";
import { IndexModelSchema } from "../lib/schemas";

const SCORE = { hi: 90, lo: 80, point: 85 } as const;
const AXIS_SCORE = {
  ...SCORE,
  n: 100,
  n_errors: 0,
  n_no_answer: 0,
  raw_accuracy: 0.85,
} as const;

describe("leaderboard scope splitting", () => {
  it("separates full-index rows, static-suite rows, and scoreless catalog shells", () => {
    const full = IndexModelSchema.parse({
      ...row("full-index", "Full Index"),
      axes: {
        agentic: AXIS_SCORE,
        coding: AXIS_SCORE,
        instruction: AXIS_SCORE,
        knowledge: AXIS_SCORE,
        tool_calling: AXIS_SCORE,
      },
      composite_full: SCORE,
      origin: "project_anchor",
      trust_label: "project_anchor",
    });
    const staticOnly = IndexModelSchema.parse({
      ...row("static-only", "Static Only"),
      axes: {
        coding: AXIS_SCORE,
        instruction: AXIS_SCORE,
        knowledge: AXIS_SCORE,
        tool_calling: AXIS_SCORE,
      },
      composite: null,
      composite_full: null,
      composite_static: SCORE,
      ranked: false,
      static_index_version: "static-suite-v1",
    });
    const catalog = IndexModelSchema.parse({
      ...row("catalog", "Catalog"),
      best_run_id: null,
      composite: null,
      ranked: false,
      score_status: "missing",
    });

    const split = splitLeaderboard([catalog, staticOnly, full]);

    expect(split.ranked.map((model) => model.slug)).toEqual(["full-index"]);
    expect(split.staticComposite.map((model) => model.slug)).toEqual(["static-only"]);
    expect(split.catalog.map((model) => model.slug)).toEqual(["catalog"]);
  });
});

function row(slug: string, label: string): Record<string, unknown> {
  return {
    axes: {},
    best_run_id: `${slug}-run`,
    composite: SCORE,
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "community",
    lane: "capped-thinking",
    model_label: label,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug,
    tier: "standard",
    tokens_to_answer_median: 128,
  };
}

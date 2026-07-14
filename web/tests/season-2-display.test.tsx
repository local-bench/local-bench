import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomeLeaderboard, sortLeaderboardRows } from "../components/home-leaderboard";
import { INDEX_VERSION_V3, INDEX_VERSION_V4, displayIndexVersion, headlineScoreForDisplay } from "../lib/scoring-seasons";
import { IndexModelSchema, ModelSlugSchema, RunIdSchema, type IndexModel } from "../lib/schemas";

const SCORE = {
  hi: 72,
  lo: 68,
  n: 50,
  n_errors: 0,
  n_no_answer: 0,
  point: 70,
  raw_accuracy: 0.7,
} as const;

describe("additive season board display", () => {
  it("renders the season-1 fixture identically when season metadata is absent or explicitly v3", () => {
    const row = fixture("v1", 42);
    const legacy = renderToStaticMarkup(createElement(HomeLeaderboard, { models: [row] }));
    const explicit = renderToStaticMarkup(
      createElement(HomeLeaderboard, { models: [row], indexVersion: INDEX_VERSION_V3 }),
    );

    expect(explicit).toBe(legacy);
  });

  it("feature-detects a complete v4 row, replaces the old columns, and surfaces facets, diagnostics, and bridge scale", () => {
    const row = season2Fixture("v4", 64, 41);
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, { models: [row], indexVersion: INDEX_VERSION_V4 }),
    );

    expect(html).toContain("index-v4.0");
    expect(html).toContain("Tool use");
    expect(html).not.toContain("Tool calling");
    expect(html).not.toContain("Static Index");
    expect(html).toContain("facet breakdown");
    expect(html).toContain("Agentic · 59%");
    expect(html).toContain("Multi-turn tool control · 41%");
    // Column header carries the facet split without expanding the breakdown (owner ask, 07-15).
    expect(html).toContain("agentic 59% · multi-turn tool control 41%");
    expect(html).toContain("Diagnostics · unweighted");
    expect(html).toContain("BFCL single-turn");
    expect(html).toContain("index-v3.0 bridge 41.0");
  });

  it("keeps an incomplete Option-D anchor on its v3 label and composite and never shows its partial v4 value", () => {
    const complete = season2Fixture("complete", 61, 40);
    const anchor = IndexModelSchema.parse({
      ...rawFixture("anchor", 33),
      composite_full: { hi: 100, lo: 98, point: 99 },
      index_version: INDEX_VERSION_V4,
      axes: { knowledge: SCORE, instruction: SCORE, coding: SCORE, math: SCORE },
    });
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, { models: [complete, anchor], indexVersion: INDEX_VERSION_V4 }),
    );

    expect(displayIndexVersion(anchor)).toBe(INDEX_VERSION_V3);
    expect(headlineScoreForDisplay(anchor)?.point).toBe(33);
    expect(html).toContain("index-v3.0");
    expect(html).not.toContain(">99.0<");
  });

  it("sorts only inside an index version and preserves season-group order", () => {
    const rows = [
      fixture("v3-low", 20),
      season2Fixture("v4-low", 30, 10),
      fixture("v3-high", 80),
      season2Fixture("v4-high", 70, 10),
    ];

    expect(sortLeaderboardRows(rows, { key: "composite", direction: "desc" }).map((row) => row.slug)).toEqual([
      "v3-high",
      "v3-low",
      "v4-high",
      "v4-low",
    ]);
  });
});

function season2Fixture(slug: string, v4Point: number, v3Point: number): IndexModel {
  const facet = (point: number, bench: string, weight: number) => ({
    ...SCORE,
    point,
    bench,
    weight,
  });
  return IndexModelSchema.parse({
    ...rawFixture(slug, v3Point),
    index_version: INDEX_VERSION_V4,
    composite_full: { hi: v4Point + 1, lo: v4Point - 1, point: v4Point },
    legacy_composite: { hi: v3Point + 1, lo: v3Point - 1, point: v3Point },
    season_bridge: {
      season_1: { index_version: INDEX_VERSION_V3, composite_v3: { hi: v3Point + 1, lo: v3Point - 1, point: v3Point } },
      season_2: { index_version: INDEX_VERSION_V4, composite_v4: { hi: v4Point + 1, lo: v4Point - 1, point: v4Point } },
    },
    axes: {
      tool_use: {
        ...SCORE,
        point: 55,
        facets: {
          agentic: facet(50, "appworld_c", 10 / 17),
          multi_turn_tool_control: facet(60, "bfcl_multi_turn_base", 7 / 17),
        },
      },
      knowledge: SCORE,
      instruction: SCORE,
      coding: SCORE,
      math: SCORE,
      call_formatting: { ...SCORE, point: 45 },
      bfcl_single_turn: { ...SCORE, point: 44 },
    },
  });
}

function fixture(slug: string, point: number): IndexModel {
  return IndexModelSchema.parse(rawFixture(slug, point));
}

function rawFixture(slug: string, point: number): Record<string, unknown> {
  return {
    axes: {},
    best_run_id: RunIdSchema.parse(`${slug}-run`),
    composite: { hi: point + 1, lo: point - 1, point },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "anchor",
    lane: "bounded-final-v2",
    model_label: slug,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: ModelSlugSchema.parse(slug),
    tier: "standard",
    tokens_to_answer_median: 128,
  };
}

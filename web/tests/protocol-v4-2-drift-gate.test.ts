import { describe, expect, it } from "vitest";
import protocol from "../../protocol/index-v4.2.json";
import { axisColumns } from "../components/leaderboard-table-cells";
import { publicProtocolLabel } from "../lib/board-adapter";
import { HEADLINE_AXIS_COUNT } from "../functions/_lib/submission-publish-validation";
import {
  INDEX_VERSION_V4_1,
  INDEX_VERSION_V4_2,
  SEASON_2_DIAGNOSTICS,
  SEASON_2_HEADLINE_AXES,
  SEASON_2_WEIGHT_QUALIFIER,
  TOOL_USE_FACETS,
  hasCompleteSeason2Coverage,
} from "../lib/scoring-seasons";
import { IndexModelSchema, ModelSlugSchema, RunIdSchema, type IndexModel } from "../lib/schemas";

const POINT = {
  hi: 51,
  lo: 49,
  n: 1,
  n_errors: 0,
  n_no_answer: 0,
  point: 50,
  raw_accuracy: 0.5,
} as const;

describe("index-v4.2 protocol manifest drift gate", () => {
  it("keeps web headline constants, facets, diagnostics, and display order aligned", () => {
    const headline = protocol.axes.filter((axis) => axis.role === "headline");
    const byKey = new Map(headline.map((axis) => [axis.key, axis]));
    const expectedWebHeadline = protocol.headline_axis_order.map((key) => byKey.get(key)?.web_key);
    const manifestToolUse = byKey.get("tool_use");

    expect(INDEX_VERSION_V4_2).toBe(protocol.protocol_id);
    expect(SEASON_2_HEADLINE_AXES).toEqual(expectedWebHeadline);
    expect(SEASON_2_WEIGHT_QUALIFIER).toBe(protocol.qualifier_weights);
    expect(TOOL_USE_FACETS.map(({ key, bench, weight }) => ({ key, bench, weight }))).toEqual(
      manifestToolUse?.facets,
    );
    expect(SEASON_2_DIAGNOSTICS.map(({ key, label, bench }) => ({ key, label, bench }))).toEqual(
      protocol.diagnostics,
    );
    expect(axisColumns([projectRow()])).toEqual(protocol.web_axis_columns);
    expect(publicProtocolLabel(INDEX_VERSION_V4_2)).toBe(protocol.public_tag);
    expect(publicProtocolLabel(INDEX_VERSION_V4_1)).toBe("LB-2026-07");
    expect(HEADLINE_AXIS_COUNT).toBe(protocol.headline_axis_count);
  });

  it("requires manifest denominators only for current project index rows", () => {
    const project = projectRow();
    const wrongAgentic = IndexModelSchema.parse({
      ...project,
      axes: { ...project.axes, tool_use: { ...project.axes["tool_use"], n: 95 } },
    });
    const communityLegacyShape = IndexModelSchema.parse({
      ...wrongAgentic,
      origin: "community",
    });
    const archivedV41 = IndexModelSchema.parse({
      ...wrongAgentic,
      index_version: INDEX_VERSION_V4_1,
    });

    expect(hasCompleteSeason2Coverage(project)).toBe(true);
    expect(hasCompleteSeason2Coverage(wrongAgentic)).toBe(false);
    expect(hasCompleteSeason2Coverage(communityLegacyShape)).toBe(true);
    expect(hasCompleteSeason2Coverage(archivedV41)).toBe(true);
  });

  it("does not make diagnostic coverage part of rank eligibility", () => {
    const withoutDiagnostics = projectRow();
    const withDiagnostics = IndexModelSchema.parse({
      ...withoutDiagnostics,
      diagnostics: {
        multi_turn_tool_control: { ...POINT, n: 50, point: 24, raw_accuracy: 0.24 },
      },
    });

    expect(hasCompleteSeason2Coverage(withoutDiagnostics)).toBe(true);
    expect(hasCompleteSeason2Coverage(withDiagnostics)).toBe(true);
  });
});

function projectRow(): IndexModel {
  const denominators = protocol.expected_denominators;
  return IndexModelSchema.parse({
    axes: {
      tool_use: { ...POINT, n: denominators.tool_use },
      knowledge: { ...POINT, n: denominators.knowledge },
      instruction: { ...POINT, n: denominators.instruction },
      coding: { ...POINT, n: denominators.coding },
      math: { ...POINT, n: denominators.math },
    },
    best_run_id: RunIdSchema.parse("protocol-v42-run"),
    composite: POINT,
    composite_full: POINT,
    demo: false,
    est_cost_usd: null,
    family: "Protocol fixture",
    gpu: null,
    index_version: INDEX_VERSION_V4_2,
    kind: "maintainer_project",
    lane: "bounded-final-v2",
    model_label: "Protocol fixture",
    n_runs: 1,
    origin: "project_anchor",
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: ModelSlugSchema.parse("protocol-v42"),
    tier: "standard",
    tokens_to_answer_median: 128,
  });
}

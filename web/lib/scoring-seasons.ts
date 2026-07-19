import type { AxisScore, IndexModel, Score } from "./schemas";
import { publicProtocolLabel } from "./board-adapter";

type SeasonScoredRow = {
  readonly axes: Record<string, AxisScore>;
  readonly composite: Score | null;
  readonly composite_full?: Score | null | undefined;
  readonly legacy_composite?: Score | null | undefined;
  readonly index_version?: string | undefined;
  readonly season_bridge?: {
    readonly season_1: { readonly composite_v3: Score };
  } | undefined;
};

export const INDEX_VERSION_V3 = "index-v3.0";
// index-v4.1 (2026-07-17 reweight): the Agentic macro-axis (structural key
// "tool_use" — data keys never changed) rose 20% -> 25%; the other four
// headline axes were scaled by 15/16 (24 -> 22.5 x3, 8 -> 7.5). index-v4.0
// (20/24/24/24/8, axis label "Tool use") is a distinct historical scale.
export const INDEX_VERSION_V4 = "index-v4.1";
export const SEASON_2_INDEX_QUALIFIER = `${publicProtocolLabel(INDEX_VERSION_V4)} | 25/22.5/22.5/22.5/7.5`;
export const SEASON_2_INDEX_PROFILE = "Profile: Agentic / Knowledge / Instruction / Coding / Math";

export const SEASON_2_HEADLINE_AXES = [
  "tool_use",
  "knowledge",
  "instruction",
  "coding",
  "math",
] as const;

// Identifiers keep the TOOL_USE_* prefix because they mirror the frozen
// structural key "tool_use"; the user-facing label is "Agentic".
export const TOOL_USE_WEIGHT = 0.25;

export const TOOL_USE_FACETS = [
  {
    key: "agentic",
    label: "AppWorld (agentic execution)",
    bench: "appworld_c",
    weight: 10 / 17,
    construct: "Observation-conditioned iterative agency (AppWorld Test-Normal task-goal completion)",
  },
  {
    key: "multi_turn_tool_control",
    label: "Multi-turn tool control",
    bench: "bfcl_multi_turn_base",
    weight: 7 / 17,
    construct: "Stateful tool sequencing across the BFCL multi-turn base split",
  },
] as const;

// One-line facet split for column headers ("agentic 59% · multi-turn tool control 41%"),
// derived from TOOL_USE_FACETS so header copy can never drift from the declared weights.
export const TOOL_USE_FACET_QUALIFIER = TOOL_USE_FACETS.map(
  (facet) => `${facet.label.toLowerCase()} ${Math.round(facet.weight * 100)}%`,
).join(" · ");

export const SEASON_2_DIAGNOSTICS = [
  { key: "call_formatting", label: "Call formatting", bench: "tc_json_v1", coverageRequired: true },
  { key: "bfcl_single_turn", label: "BFCL single-turn" },
  { key: "bfcl_multi_turn_long_context", label: "BFCL multi-turn long-context" },
  { key: "long_context", label: "RULER 32K", bench: "ruler_32k" },
] as const;

function measuredAxis(model: SeasonScoredRow, axis: string): boolean {
  const score = model.axes[axis];
  return score !== undefined && score.n > 0;
}

/**
 * Feature detection for the additive season-2 view. A declared v4 label is not enough:
 * Option-D anchors remain on their v3 label and score until the strict v4 profile is complete.
 */
export function hasCompleteSeason2Coverage(model: SeasonScoredRow): boolean {
  return (
    model.index_version === INDEX_VERSION_V4 &&
    model.composite_full !== null &&
    model.composite_full !== undefined &&
    SEASON_2_HEADLINE_AXES.every((axis) => measuredAxis(model, axis))
  );
}

export function displayIndexVersion(model: SeasonScoredRow): typeof INDEX_VERSION_V3 | typeof INDEX_VERSION_V4 {
  return hasCompleteSeason2Coverage(model) ? INDEX_VERSION_V4 : INDEX_VERSION_V3;
}

export function isSeason2Board(models: readonly IndexModel[], _boardIndexVersion?: string): boolean {
  return models.some(hasCompleteSeason2Coverage);
}

export function headlineScoreForDisplay(model: SeasonScoredRow): Score | null {
  if (hasCompleteSeason2Coverage(model)) {
    return model.composite_full ?? null;
  }
  if (model.index_version !== INDEX_VERSION_V4) {
    return model.composite_full ?? model.composite;
  }
  return model.season_bridge?.season_1.composite_v3 ?? model.legacy_composite ?? model.composite;
}

export function legacyBridgeScore(model: SeasonScoredRow): Score | null {
  if (!hasCompleteSeason2Coverage(model)) {
    return null;
  }
  return model.season_bridge?.season_1.composite_v3 ?? model.legacy_composite ?? null;
}

export function diagnosticScores(model: IndexModel): readonly { readonly key: string; readonly label: string; readonly score: IndexModel["axes"][string] }[] {
  return SEASON_2_DIAGNOSTICS.flatMap((diagnostic) => {
    const score = model.diagnostics?.[diagnostic.key] ?? model.axes[diagnostic.key];
    return score === undefined ? [] : [{ key: diagnostic.key, label: diagnostic.label, score }];
  });
}

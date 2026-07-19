import type { AxisScore, IndexModel, Score } from "./schemas";
import { publicProtocolLabel } from "./board-adapter";

type SeasonScoredRow = {
  readonly axes: Record<string, AxisScore>;
  readonly composite: Score | null;
  readonly composite_full?: Score | null | undefined;
  readonly legacy_composite?: Score | null | undefined;
  readonly index_version?: string | undefined;
  readonly origin?: string | undefined;
  readonly season_bridge?: {
    readonly season_1: { readonly composite_v3: Score };
  } | undefined;
};

export const INDEX_VERSION_V3 = "index-v3.0";
export const INDEX_VERSION_V4_1 = "index-v4.1";
export const INDEX_VERSION_V4_2 = "index-v4.2";
export const INDEX_VERSION_V4 = INDEX_VERSION_V4_2;
export const SEASON_2_WEIGHT_QUALIFIER = "25/22.5/22.5/22.5/7.5";
export const SEASON_2_INDEX_QUALIFIER = `${publicProtocolLabel(INDEX_VERSION_V4)} | ${SEASON_2_WEIGHT_QUALIFIER}`;
export const SEASON_2_INDEX_PROFILE = "Profile: Agentic / Knowledge / Instruction / Coding / Math";

export const SEASON_2_HEADLINE_AXES = [
  "tool_use",
  "knowledge",
  "instruction",
  "coding",
  "math",
] as const;

export const EXPECTED_SEASON_2_DENOMINATORS = {
  tool_use: 96,
  knowledge: 400,
  instruction: 294,
  // Coding is scored over the 141 sandbox-scoreable BigCodeBench-Hard items in
  // BOTH lanes (the 7 network/data-dependent items are excluded, per the public
  // methodology); legacy inclusive-n aggregates are normalized at rescore time.
  coding: 141,
  math: 139,
} as const satisfies Readonly<Record<(typeof SEASON_2_HEADLINE_AXES)[number], number>>;

// Identifiers keep the TOOL_USE_* prefix because they mirror the frozen
// structural key "tool_use"; the user-facing label is "Agentic".
export const TOOL_USE_WEIGHT = 0.25;

export const TOOL_USE_FACETS = [
  {
    key: "agentic",
    label: "AppWorld task-goal completion",
    bench: "appworld_c",
    weight: 1,
    construct: "Observation-conditioned iterative agency (AppWorld Test-Normal task-goal completion)",
  },
] as const;

export const SEASON_2_DIAGNOSTICS = [
  { key: "call_formatting", label: "Call formatting", bench: "tc_json_v1" },
  { key: "bfcl_single_turn", label: "BFCL single-turn", bench: "bfcl" },
  {
    key: "multi_turn_tool_control",
    label: "BFCL v3 multi-turn base — frozen snapshot",
    bench: "bfcl_multi_turn_base",
  },
  {
    key: "bfcl_multi_turn_long_context",
    label: "BFCL multi-turn long-context",
    bench: "bfcl_multi_turn_long_context",
  },
  { key: "long_context", label: "RULER 32K", bench: "ruler_32k" },
] as const;

function measuredAxis(model: SeasonScoredRow, axis: string): boolean {
  const score = model.axes[axis];
  return score !== undefined && score.n > 0;
}

function hasExpectedProjectDenominators(model: SeasonScoredRow): boolean {
  if (model.index_version !== INDEX_VERSION_V4_2 || model.origin !== "project_anchor") return true;
  return SEASON_2_HEADLINE_AXES.every(
    (axis) => model.axes[axis]?.n === EXPECTED_SEASON_2_DENOMINATORS[axis],
  );
}

/**
 * Feature detection for the additive season-2 view. A declared v4 label is not enough:
 * Option-D anchors remain on their v3 label and score until the strict v4 profile is complete.
 */
export function hasCompleteSeason2Coverage(model: SeasonScoredRow): boolean {
  return (
    (model.index_version === INDEX_VERSION_V4_1 || model.index_version === INDEX_VERSION_V4_2) &&
    model.composite_full !== null &&
    model.composite_full !== undefined &&
    SEASON_2_HEADLINE_AXES.every((axis) => measuredAxis(model, axis)) &&
    hasExpectedProjectDenominators(model)
  );
}

export function displayIndexVersion(
  model: SeasonScoredRow,
): typeof INDEX_VERSION_V3 | typeof INDEX_VERSION_V4_1 | typeof INDEX_VERSION_V4_2 {
  if (
    hasCompleteSeason2Coverage(model)
    && (model.index_version === INDEX_VERSION_V4_1 || model.index_version === INDEX_VERSION_V4_2)
  ) {
    return model.index_version;
  }
  return INDEX_VERSION_V3;
}

export function isSeason2Board(models: readonly IndexModel[], _boardIndexVersion?: string): boolean {
  return models.some(hasCompleteSeason2Coverage);
}

export function headlineScoreForDisplay(model: SeasonScoredRow): Score | null {
  if (hasCompleteSeason2Coverage(model)) {
    return model.composite_full ?? null;
  }
  if (model.index_version !== INDEX_VERSION_V4_1 && model.index_version !== INDEX_VERSION_V4_2) {
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

export function diagnosticScores(model: IndexModel): readonly {
  readonly key: string;
  readonly label: string;
  readonly score: IndexModel["axes"][string] | undefined;
}[] {
  return SEASON_2_DIAGNOSTICS.map((diagnostic) => ({
    key: diagnostic.key,
    label: diagnostic.label,
    score: model.diagnostics?.[diagnostic.key]
      ?? model.axes[diagnostic.key]
      ?? model.axes[diagnostic.bench],
  }));
}

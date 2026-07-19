import type { IndexModel, Score } from "./schemas";
import {
  hasCompleteSeason2Coverage,
  headlineScoreForDisplay,
  INDEX_VERSION_V4_1,
  INDEX_VERSION_V4_2,
} from "./scoring-seasons";

export type LeaderboardScoreMode = "full" | "static";

// The single headline lane of the ranked board. Every lane-scoped view (board split,
// efficiency scatter) keys off this constant so a lane migration is one edit, not a hunt.
// Rows measured under other lanes (legacy capped-thinking, answer-only ablations) stay on
// model detail pages as diagnostics.
export const HEADLINE_LANE = "bounded-final-v2";

export function scoreForMode(model: IndexModel, mode: LeaderboardScoreMode): Score | null {
  switch (mode) {
    case "full":
      return headlineScoreForDisplay(model);
    case "static":
      return model.composite_static ?? null;
    default:
      return assertNever(mode);
  }
}

export function hasAgenticAxis(model: IndexModel): boolean {
  return model.axes["agentic"] !== undefined;
}

export function isFullIndexRow(model: IndexModel): boolean {
  return (
    model.score_status === "measured" &&
    model.lane === HEADLINE_LANE &&
    !model.demo &&
    hasCompleteHeadlineCoverage(model) &&
    scoreForMode(model, "full") !== null
  );
}

export function hasCompleteHeadlineCoverage(model: IndexModel): boolean {
  if (model.index_version === INDEX_VERSION_V4_1 || model.index_version === INDEX_VERSION_V4_2) {
    return hasCompleteSeason2Coverage(model);
  }
  return ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => {
    const score = model.axes[axis];
    return score !== undefined && score.n > 0;
  });
}

export function isStaticCompositeRow(model: IndexModel): boolean {
  return (
    model.score_status === "measured" &&
    !model.ranked &&
    model.lane === HEADLINE_LANE &&
    model.tier === "standard" &&
    model.conformance_status === "headline-comparable" &&
    !model.demo &&
    model.composite_full == null &&
    model.composite_static !== null &&
    model.composite_static !== undefined &&
    model.static_index_version === "static-suite-v2" &&
    hasStaticAxes(model) &&
    hasStaticTrustEvidence(model)
  );
}

export function staticIndexStatus(model: IndexModel): "verified" | "provisional" | null {
  if (model.composite_static === null || model.composite_static === undefined) {
    return null;
  }
  if (model.static_index_version !== "static-suite-v2" || !hasStaticAxes(model) || !hasStaticTrustEvidence(model)) {
    return null;
  }
  return isFullIndexRow(model) && model.tier === "standard" && model.conformance_status === "headline-comparable"
    ? "verified"
    : "provisional";
}

function hasStaticAxes(model: IndexModel): boolean {
  return ["knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => model.axes[axis] !== undefined);
}

function hasStaticTrustEvidence(model: IndexModel): boolean {
  return model.trust_label === "project_anchor" && model.verdict_source === "verifier";
}

function assertNever(value: never): never {
  throw new Error(`Unhandled leaderboard score mode: ${String(value)}`);
}

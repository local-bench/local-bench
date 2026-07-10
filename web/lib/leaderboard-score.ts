import type { IndexModel, Score } from "./schemas";

export type LeaderboardScoreMode = "full" | "static";

// The single headline lane of the ranked board. Every lane-scoped view (board split,
// efficiency scatter) keys off this constant so a lane migration is one edit, not a hunt.
// Rows measured under other lanes (legacy capped-thinking, answer-only ablations) stay on
// model detail pages as diagnostics.
export const HEADLINE_LANE = "bounded-final-v2";

export function scoreForMode(model: IndexModel, mode: LeaderboardScoreMode): Score | null {
  switch (mode) {
    case "full":
      return model.composite_full ?? model.composite;
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
    model.ranked &&
    model.lane === HEADLINE_LANE &&
    !model.demo &&
    scoreForMode(model, "full") !== null
  );
}

export function isStaticCompositeRow(model: IndexModel): boolean {
  return (
    model.score_status === "measured" &&
    !model.ranked &&
    model.lane === HEADLINE_LANE &&
    !model.demo &&
    model.composite_full == null &&
    model.composite_static !== null &&
    model.composite_static !== undefined &&
    model.static_index_version === "static-suite-v2"
  );
}

export function staticIndexStatus(model: IndexModel): "verified" | "provisional" | null {
  if (model.composite_static === null || model.composite_static === undefined) {
    return null;
  }
  return isFullIndexRow(model) ? "verified" : "provisional";
}

function assertNever(value: never): never {
  throw new Error(`Unhandled leaderboard score mode: ${String(value)}`);
}

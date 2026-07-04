import type { IndexModel, Score } from "./schemas";

export type LeaderboardScoreMode = "full" | "static";

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
    model.lane === "capped-thinking" &&
    !model.demo &&
    scoreForMode(model, "full") !== null
  );
}

export function isStaticCompositeRow(model: IndexModel): boolean {
  return (
    model.score_status === "measured" &&
    !model.ranked &&
    model.lane === "capped-thinking" &&
    !model.demo &&
    model.composite_full == null &&
    model.composite_static !== null &&
    model.composite_static !== undefined &&
    model.static_index_version === "static-suite-v1"
  );
}

function assertNever(value: never): never {
  throw new Error(`Unhandled leaderboard score mode: ${String(value)}`);
}

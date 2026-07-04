import { runtimeSortLabel } from "./runtime-display";
import { scoreForMode, type LeaderboardScoreMode } from "./leaderboard-score";
import type { AgenticModel, IndexModel } from "./schemas";

export const AGENTIC_SORT_KEY = "agentic_experimental";

const EMPTY_AGENTIC: ReadonlyMap<string, AgenticModel> = new Map();

export type SortKey = string;
export type SortDirection = "asc" | "desc";

export type SortState = {
  readonly key: SortKey;
  readonly direction: SortDirection;
};

export type LeaderboardSortOptions = {
  readonly agenticBySlug?: ReadonlyMap<string, AgenticModel>;
  readonly scoreMode?: LeaderboardScoreMode;
};

type CompareContext = {
  readonly agenticBySlug: ReadonlyMap<string, AgenticModel>;
  readonly key: SortKey;
  readonly scoreMode: LeaderboardScoreMode;
};

export function sortLeaderboardRows(
  models: readonly IndexModel[],
  sort: SortState,
  options: LeaderboardSortOptions = {},
): readonly IndexModel[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  const context: CompareContext = {
    agenticBySlug: options.agenticBySlug ?? EMPTY_AGENTIC,
    key: sort.key,
    scoreMode: options.scoreMode ?? "full",
  };
  return [...models].sort((left, right) => compareRows(left, right, context) * direction);
}

export function buildLaneRanks(
  models: readonly IndexModel[],
  scoreMode: LeaderboardScoreMode,
): ReadonlyMap<string, number> {
  const groups = new Map<string, readonly IndexModel[]>();
  for (const model of models) {
    if (!model.ranked && scoreMode === "full") {
      continue;
    }
    const lane = model.lane ?? "n/a";
    const group = groups.get(lane) ?? [];
    groups.set(lane, [...group, model]);
  }

  const ranks = new Map<string, number>();
  for (const group of groups.values()) {
    const rankedGroup = sortLeaderboardRows(group, { key: "composite", direction: "desc" }, { scoreMode });
    rankedGroup.forEach((model, index) => {
      ranks.set(model.slug, index + 1);
    });
  }
  return ranks;
}

function compareRows(left: IndexModel, right: IndexModel, context: CompareContext): number {
  switch (context.key) {
    case "model":
      return left.model_label.localeCompare(right.model_label);
    case "kind":
      return left.kind.localeCompare(right.kind);
    case "composite":
      return nullableNumber(scoreForMode(left, context.scoreMode)?.point ?? null) - nullableNumber(scoreForMode(right, context.scoreMode)?.point ?? null);
    case AGENTIC_SORT_KEY:
      return nullableNumber(context.agenticBySlug.get(left.slug)?.asr_pct ?? null) - nullableNumber(context.agenticBySlug.get(right.slug)?.asr_pct ?? null);
    case "tokens":
      return nullableNumber(left.tokens_to_answer_median) - nullableNumber(right.tokens_to_answer_median);
    case "hardware":
      return (left.gpu?.name ?? "").localeCompare(right.gpu?.name ?? "");
    case "runtime":
      return runtimeSortLabel(left.runtime).localeCompare(runtimeSortLabel(right.runtime));
    case "user":
      return displaySubmitter(left).localeCompare(displaySubmitter(right));
    case "latency":
      return nullableNumber(left.latency_s_median ?? null) - nullableNumber(right.latency_s_median ?? null);
    case "benchtime":
      return nullableNumber(left.wall_time_seconds ?? null) - nullableNumber(right.wall_time_seconds ?? null);
    default:
      return compareAxis(left, right, context.key);
  }
}

function compareAxis(left: IndexModel, right: IndexModel, axis: string): number {
  return (left.axes[axis]?.point ?? Number.NEGATIVE_INFINITY) - (right.axes[axis]?.point ?? Number.NEGATIVE_INFINITY);
}

function displaySubmitter(model: IndexModel): string {
  return model.submitter_display_name ?? model.submitted_by ?? "";
}

function nullableNumber(value: number | null): number {
  return value ?? Number.NEGATIVE_INFINITY;
}

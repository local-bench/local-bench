import { runtimeSortLabel } from "./runtime-display";
import { scoreForMode, type LeaderboardScoreMode } from "./leaderboard-score";
import type { AgenticModel, IndexModel } from "./schemas";
import { isTrustedPopulation } from "./trusted-population";
import { displayIndexVersion } from "./scoring-seasons";

export const AGENTIC_SORT_KEY = "agentic_experimental";
export const STATIC_INDEX_SORT_KEY = "static_index";

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

export type LeaderboardSortValue = number | string | null;

export function sortLeaderboardRows(
  models: readonly IndexModel[],
  sort: SortState,
  options: LeaderboardSortOptions = {},
): readonly IndexModel[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  const seasonGroups = new Map<string, IndexModel[]>();
  for (const model of models) {
    const version = displayIndexVersion(model);
    seasonGroups.set(version, [...(seasonGroups.get(version) ?? []), model]);
  }
  return [...seasonGroups.values()].flatMap((group) =>
    group.sort((left, right) => compareLeaderboardSortValues(
      leaderboardSortValue(left, sort.key, options),
      leaderboardSortValue(right, sort.key, options),
    ) * direction),
  );
}

export function buildLaneRanks(
  models: readonly IndexModel[],
  scoreMode: LeaderboardScoreMode,
): ReadonlyMap<string, number> {
  const groups = new Map<string, readonly IndexModel[]>();
  for (const model of models) {
    if (!isTrustedPopulation(model)) {
      continue;
    }
    if (!model.ranked && scoreMode === "full") {
      continue;
    }
    const lane = `${displayIndexVersion(model)}:${model.lane ?? "n/a"}`;
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

export function leaderboardSortValue(
  model: IndexModel,
  key: SortKey,
  options: LeaderboardSortOptions = {},
): LeaderboardSortValue {
  switch (key) {
    case "model":
      return model.model_label;
    case "composite":
      return scoreForMode(model, options.scoreMode ?? "full")?.point ?? null;
    case STATIC_INDEX_SORT_KEY:
      return model.composite_static?.point ?? null;
    case AGENTIC_SORT_KEY:
      return (options.agenticBySlug ?? EMPTY_AGENTIC).get(model.slug)?.asr_pct ?? null;
    case "tokens":
      return model.tokens_to_answer_median;
    case "hardware":
      return model.gpu?.name ?? "";
    case "runtime":
      return runtimeSortLabel(model.runtime);
    case "user":
      return displaySubmitter(model);
    case "latency":
      return model.latency_s_median ?? null;
    case "benchtime":
      return model.wall_time_seconds ?? null;
    default:
      return model.axes[key]?.point ?? null;
  }
}

export function compareLeaderboardSortValues(
  left: LeaderboardSortValue,
  right: LeaderboardSortValue,
): number {
  if (typeof left === "string" && typeof right === "string") return left.localeCompare(right);
  if (typeof left === "number" && typeof right === "number") return left - right;
  return nullableNumber(typeof left === "number" ? left : null)
    - nullableNumber(typeof right === "number" ? right : null);
}

function displaySubmitter(model: IndexModel): string {
  // Mirrors RunByCell: community submitter name, else "local-bench" for the project's own
  // measured rows, else empty (catalog shells / demo fixtures).
  const submitter = model.submitter_display_name ?? model.submitted_by;
  if (submitter !== null && submitter !== undefined && submitter !== "") {
    return submitter;
  }
  return model.score_status === "measured" && !model.demo ? "local-bench" : "";
}

function nullableNumber(value: number | null): number {
  return value ?? Number.NEGATIVE_INFINITY;
}

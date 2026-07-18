import type { CommunityBoardRow } from "./community-data";
import {
  AGENTIC_SORT_KEY,
  compareLeaderboardSortValues,
  leaderboardSortValue,
  STATIC_INDEX_SORT_KEY,
  type LeaderboardSortOptions,
  type LeaderboardSortValue,
  type SortKey,
  type SortState,
} from "./leaderboard-sort";
import type { IndexModel } from "./schemas";

export const UNIFIED_LEADERBOARD_FILTERS = ["all", "local-bench", "community"] as const;
export type UnifiedLeaderboardFilter = (typeof UNIFIED_LEADERBOARD_FILTERS)[number];

export type UnifiedLeaderboardRow =
  | { readonly model: IndexModel; readonly source: "local-bench" }
  | { readonly row: CommunityBoardRow; readonly source: "community" };

export function filterUnifiedLeaderboardRows(
  ranked: readonly IndexModel[],
  community: readonly CommunityBoardRow[],
  filter: UnifiedLeaderboardFilter,
): readonly UnifiedLeaderboardRow[] {
  const rankedRows = ranked.map((model): UnifiedLeaderboardRow => ({ model, source: "local-bench" }));
  const communityRows = community.map((row): UnifiedLeaderboardRow => ({ row, source: "community" }));
  switch (filter) {
    case "all":
      return [...rankedRows, ...communityRows];
    case "local-bench":
      return rankedRows;
    case "community":
      return communityRows;
    default:
      return assertNever(filter);
  }
}

export function sortUnifiedLeaderboardRows(
  rows: readonly UnifiedLeaderboardRow[],
  sort: SortState,
  options: LeaderboardSortOptions = {},
): readonly UnifiedLeaderboardRow[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const compared = compareLeaderboardSortValues(
      unifiedSortValue(left, sort.key, options),
      unifiedSortValue(right, sort.key, options),
    );
    if (compared !== 0) return compared * direction;
    return unifiedDisplayName(left).localeCompare(unifiedDisplayName(right));
  });
}

function unifiedSortValue(
  row: UnifiedLeaderboardRow,
  key: SortKey,
  options: LeaderboardSortOptions,
): LeaderboardSortValue {
  switch (row.source) {
    case "local-bench":
      return leaderboardSortValue(row.model, key, options);
    case "community":
      return communitySortValue(row.row, key);
    default:
      return assertNever(row);
  }
}

function communitySortValue(row: CommunityBoardRow, key: SortKey): LeaderboardSortValue {
  switch (key) {
    case "model":
      return row.displayName;
    case "composite":
      return row.partialComposite === null ? null : row.partialComposite * 100;
    case "user":
      return row.submitterDisplayName ?? row.submitterKeyFingerprint ?? "";
    case STATIC_INDEX_SORT_KEY:
    case AGENTIC_SORT_KEY:
    case "tokens":
    case "hardware":
    case "runtime":
    case "latency":
    case "benchtime":
      return null;
    default: {
      const axis = row.axes?.[key];
      return axis?.status === "measured" ? axis.score : null;
    }
  }
}

function unifiedDisplayName(row: UnifiedLeaderboardRow): string {
  switch (row.source) {
    case "local-bench":
      return row.model.model_label;
    case "community":
      return row.row.displayName;
    default:
      return assertNever(row);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled unified leaderboard filter: ${String(value)}`);
}

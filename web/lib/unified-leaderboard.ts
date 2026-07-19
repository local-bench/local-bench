import type { CommunityBoardRow } from "./community-data";
import { isFullIndexRow } from "./leaderboard-score";
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

export type UnifiedLeaderboardRow =
  | { readonly model: IndexModel; readonly rank: number; readonly source: "local-bench" }
  | { readonly rank: number; readonly row: CommunityBoardRow; readonly source: "community" };

type UnrankedUnifiedRow =
  | { readonly model: IndexModel; readonly source: "local-bench" }
  | { readonly row: CommunityBoardRow; readonly source: "community" };

export function filterUnifiedLeaderboardRows(
  ranked: readonly IndexModel[],
  community: readonly CommunityBoardRow[],
): readonly UnifiedLeaderboardRow[] {
  const completeCommunity = community.filter((row) => row.headlineComplete && row.compositeFull !== null);
  const rows: UnrankedUnifiedRow[] = [
    ...ranked.filter(isFullIndexRow).map((model) => ({ model, source: "local-bench" as const })),
    ...completeCommunity.map((row) => ({ row, source: "community" as const })),
  ].sort((left, right) => scoreValue(right) - scoreValue(left));
  return rows.map((row, index) => ({ ...row, rank: index + 1 }));
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
      return row.compositeFull === null ? null : normalizePercent(row.compositeFull);
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
      return axis?.status === "measured" && axis.score !== null && axis.score !== undefined
        ? normalizePercent(axis.score)
        : null;
    }
  }
}

function scoreValue(row: UnrankedUnifiedRow): number {
  switch (row.source) {
    case "local-bench":
      return row.model.composite_full?.point ?? row.model.composite?.point ?? Number.NEGATIVE_INFINITY;
    case "community":
      return row.row.compositeFull === null ? Number.NEGATIVE_INFINITY : normalizePercent(row.row.compositeFull);
    default:
      return assertNever(row);
  }
}

function normalizePercent(value: number): number {
  return value <= 1 ? value * 100 : value;
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

import type { CommunityBoardRow } from "./community-data";
import { boardAxisValue, toDisplayScore } from "./board-adapter";
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
import { runtimeSortLabel } from "./runtime-display";
import {
  EMPTY_FAMILY_RESOLUTION_CONTEXT,
  resolveFamily,
  type FamilyResolutionContext,
} from "./family-resolution";
import { selectBestPerFamily } from "./landing-best-per-base";

export type UnifiedLeaderboardRow =
  | { readonly model: IndexModel; readonly rank: number; readonly source: "local-bench" }
  | { readonly rank: number; readonly row: CommunityBoardRow; readonly source: "community" };

type UnrankedUnifiedRow =
  | { readonly model: IndexModel; readonly source: "local-bench" }
  | { readonly row: CommunityBoardRow; readonly source: "community" };

export type UnifiedLeaderboardFilterOptions = {
  readonly resolutionContext?: FamilyResolutionContext;
  readonly variants?: "all" | "best-per-family";
};

export function filterUnifiedLeaderboardRows(
  ranked: readonly IndexModel[],
  community: readonly CommunityBoardRow[],
  options: UnifiedLeaderboardFilterOptions = {},
): readonly UnifiedLeaderboardRow[] {
  const completeCommunity = community.filter((row) => row.headlineComplete && row.compositeFull !== null);
  const candidates: UnrankedUnifiedRow[] = [
    ...ranked.filter(isFullIndexRow).map((model) => ({ model, source: "local-bench" as const })),
    ...completeCommunity.map((row) => ({ row, source: "community" as const })),
  ];
  const context = options.resolutionContext ?? EMPTY_FAMILY_RESOLUTION_CONTEXT;
  const selected = options.variants === "all"
    ? candidates
    : selectBestPerFamily(candidates.map((candidate) => ({
        // Owner call (2026-07-22): every candidate — including overlay-resolved fine-tunes —
        // collapses under its base/root family key on the landing best-per-base board.
        displayedComposite: scoreValue(candidate),
        resolution: candidate.source === "local-bench"
          ? resolveFamily(candidate.model, context)
          : resolveFamily(candidate.row, context),
        source: candidate.source === "local-bench"
          ? candidate.model.origin === "community" ? "community" as const : "maintainer" as const
          : candidate.row.origin === "project_anchor" ? "maintainer" as const : "community" as const,
        value: candidate,
      }))).map((candidate) => candidate.value);
  const rows = [...selected].sort((left, right) => scoreValue(right) - scoreValue(left));
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
      return row.compositeFull === null ? null : toDisplayScore(row.compositeFull);
    case "user":
      return row.submitterDisplayName ?? row.submitterKeyFingerprint ?? "";
    case STATIC_INDEX_SORT_KEY:
    case AGENTIC_SORT_KEY:
      return null;
    case "tokens":
      return row.perf?.tokens_to_answer_median ?? null;
    case "hardware":
      return row.hardware?.gpu_name ?? "";
    case "runtime":
      return runtimeSortLabel(row.runtime);
    case "latency":
      return row.perf?.latency_s_median ?? null;
    case "benchtime":
      return row.perf?.wall_time_seconds ?? null;
    default: {
      const axis = boardAxisValue(row.axes ?? {}, key);
      return axis?.status === "measured" && axis.score !== null && axis.score !== undefined
        ? toDisplayScore(axis.score)
        : null;
    }
  }
}

function scoreValue(row: UnrankedUnifiedRow): number {
  switch (row.source) {
    case "local-bench":
      return toDisplayScore(
        row.model.composite_full?.point ?? row.model.composite?.point ?? Number.NEGATIVE_INFINITY,
      );
    case "community":
      return row.row.compositeFull === null ? Number.NEGATIVE_INFINITY : toDisplayScore(row.row.compositeFull);
    default:
      return assertNever(row);
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

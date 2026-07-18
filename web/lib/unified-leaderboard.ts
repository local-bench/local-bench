import type { CommunityBoardRow } from "./community-data";
import type { IndexModel } from "./schemas";

export const UNIFIED_LEADERBOARD_FILTERS = ["all", "local-bench", "community"] as const;
export type UnifiedLeaderboardFilter = (typeof UNIFIED_LEADERBOARD_FILTERS)[number];

export type UnifiedLeaderboardRows = {
  readonly ranked: readonly IndexModel[];
  readonly community: readonly CommunityBoardRow[];
};

export function filterUnifiedLeaderboardRows(
  ranked: readonly IndexModel[],
  community: readonly CommunityBoardRow[],
  filter: UnifiedLeaderboardFilter,
): UnifiedLeaderboardRows {
  const orderedCommunity = [...community].sort(
    (left, right) =>
      (right.partialComposite ?? Number.NEGATIVE_INFINITY)
      - (left.partialComposite ?? Number.NEGATIVE_INFINITY)
      || left.displayName.localeCompare(right.displayName),
  );
  switch (filter) {
    case "all":
      return { ranked, community: orderedCommunity };
    case "local-bench":
      return { ranked, community: [] };
    case "community":
      return { ranked: [], community: orderedCommunity };
    default:
      return assertNever(filter);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled unified leaderboard filter: ${String(value)}`);
}

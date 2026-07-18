"use client";

import { useMemo, useState } from "react";
import { BoardScopeHeader } from "@/components/board-scope-header";
import { LeaderboardTable } from "@/components/leaderboard-table";
import { axisColumns } from "@/components/leaderboard-table-cells";
import type { CommunityBoardRow } from "@/lib/community-data";
import { type LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { buildLaneRanks, sortLeaderboardRows, type SortState } from "@/lib/leaderboard-sort";
import type { AgenticModel, IndexModel } from "@/lib/schemas";
import { INDEX_VERSION_V4, isSeason2Board } from "@/lib/scoring-seasons";
import {
  filterUnifiedLeaderboardRows,
  type UnifiedLeaderboardFilter,
} from "@/lib/unified-leaderboard";

const EMPTY_AGENTIC: ReadonlyMap<string, AgenticModel> = new Map();
const EMPTY_COMMUNITY: readonly CommunityBoardRow[] = [];
const EMPTY_LINEAGE: ReadonlyMap<string, string> = new Map();

export { sortLeaderboardRows } from "@/lib/leaderboard-sort";
export { filterUnifiedLeaderboardRows } from "@/lib/unified-leaderboard";

type HomeLeaderboardProps = {
  readonly agenticBySlug?: ReadonlyMap<string, AgenticModel>;
  readonly communityRows?: readonly CommunityBoardRow[];
  readonly fineTuneBaseBySlug?: ReadonlyMap<string, string>;
  readonly indexVersion?: string;
  readonly models: readonly IndexModel[];
  readonly scoreMode?: LeaderboardScoreMode;
};

export function HomeLeaderboard({
  models,
  agenticBySlug = EMPTY_AGENTIC,
  communityRows = EMPTY_COMMUNITY,
  scoreMode = "full",
  fineTuneBaseBySlug = EMPTY_LINEAGE,
  indexVersion,
}: HomeLeaderboardProps) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });
  const [filter, setFilter] = useState<UnifiedLeaderboardFilter>("all");
  const axisKeys = useMemo(() => axisColumns(models), [models]);
  const sortedModels = useMemo(
    () => sortLeaderboardRows(models, sort, { agenticBySlug, scoreMode }),
    [models, sort, agenticBySlug, scoreMode],
  );
  const visibleRows = useMemo(
    () => filterUnifiedLeaderboardRows(sortedModels, communityRows, scoreMode === "full" ? filter : "local-bench"),
    [sortedModels, communityRows, scoreMode, filter],
  );
  const laneRanks = useMemo(() => buildLaneRanks(models, scoreMode), [models, scoreMode]);
  const season2 = scoreMode === "full" && isSeason2Board(models, indexVersion);
  const showAgenticColumn = scoreMode === "full" && !season2;
  const showStaticIndexColumn = scoreMode === "full" && !season2;
  const empty = visibleRows.ranked.length === 0 && visibleRows.community.length === 0;

  return (
    <div
      data-testid={scoreMode === "static" ? "static-leaderboard" : "full-leaderboard"}
      className={scoreMode === "static"
        ? "overflow-hidden rounded-lg border border-bench-line/70 bg-bench-panel/45 opacity-90"
        : "overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20"}
    >
      <BoardScopeHeader mode={scoreMode} indexVersion={season2 ? INDEX_VERSION_V4 : indexVersion} />
      {scoreMode === "full" ? (
        <LeaderboardFilter
          communityCount={communityRows.length}
          filter={filter}
          rankedCount={models.length}
          setFilter={setFilter}
        />
      ) : null}
      {empty ? (
        <div className="px-4 py-8 text-sm leading-6 text-bench-muted">
          <div className="font-semibold text-bench-text">No rows match this filter</div>
          <div className="mt-1 max-w-3xl">
            Ranked rows require the complete current profile. Community rows appear after strict publication validation.
          </div>
        </div>
      ) : (
        <LeaderboardTable
          agenticBySlug={agenticBySlug}
          axisKeys={axisKeys}
          communityRows={visibleRows.community}
          fineTuneBaseBySlug={fineTuneBaseBySlug}
          laneRanks={laneRanks}
          models={visibleRows.ranked}
          scoreMode={scoreMode}
          season2={season2}
          setSort={setSort}
          showAgenticColumn={showAgenticColumn}
          showStaticIndexColumn={showStaticIndexColumn}
          sort={sort}
        />
      )}
    </div>
  );
}

function LeaderboardFilter({
  communityCount,
  filter,
  rankedCount,
  setFilter,
}: {
  readonly communityCount: number;
  readonly filter: UnifiedLeaderboardFilter;
  readonly rankedCount: number;
  readonly setFilter: (filter: UnifiedLeaderboardFilter) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bench-line px-3 py-3">
      <div className="flex flex-wrap gap-2" aria-label="Leaderboard source filter">
        <FilterButton active={filter === "all"} label="All" onClick={() => setFilter("all")} />
        <FilterButton active={filter === "local-bench"} label="local-bench runs" onClick={() => setFilter("local-bench")} />
        <FilterButton active={filter === "community"} label="community" onClick={() => setFilter("community")} />
      </div>
      <p className="font-mono text-xs text-bench-muted">{rankedCount} ranked · {communityCount} community</p>
    </div>
  );
}

function FilterButton({ active, label, onClick }: { readonly active: boolean; readonly label: string; readonly onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={active
        ? "rounded border border-bench-accent/50 bg-bench-accent/10 px-3 py-1.5 text-xs font-semibold text-bench-accent"
        : "rounded border border-bench-line px-3 py-1.5 text-xs font-semibold text-bench-muted transition-colors hover:border-bench-line-strong hover:text-bench-text"}
    >
      {label}
    </button>
  );
}

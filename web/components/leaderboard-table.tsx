import { AgenticHeaderLabel } from "@/components/agentic-column";
import { CommunityLeaderboardRow } from "@/components/community-leaderboard-row";
import { LeaderboardRankedRow } from "@/components/leaderboard-ranked-row";
import {
  CompositeHeaderLabel,
  SortableHeader,
  StaticIndexHeaderLabel,
  ToolUseHeaderLabel,
} from "@/components/leaderboard-table-cells";
import { axisLabel } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { AGENTIC_SORT_KEY, STATIC_INDEX_SORT_KEY, type SortState } from "@/lib/leaderboard-sort";
import type { AgenticModel, IndexModel } from "@/lib/schemas";

type LeaderboardTableProps = {
  readonly agenticBySlug: ReadonlyMap<string, AgenticModel>;
  readonly axisKeys: readonly string[];
  readonly communityRows: readonly CommunityBoardRow[];
  readonly fineTuneBaseBySlug: ReadonlyMap<string, string>;
  readonly laneRanks: ReadonlyMap<string, number>;
  readonly models: readonly IndexModel[];
  readonly scoreMode: LeaderboardScoreMode;
  readonly season2: boolean;
  readonly setSort: (sort: SortState) => void;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
  readonly sort: SortState;
};

export function LeaderboardTable({
  agenticBySlug,
  axisKeys,
  communityRows,
  fineTuneBaseBySlug,
  laneRanks,
  models,
  scoreMode,
  season2,
  setSort,
  showAgenticColumn,
  showStaticIndexColumn,
  sort,
}: LeaderboardTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[1280px] border-collapse text-sm">
        <caption className="sr-only">
          Ranked local-bench rows appear first. Community rows are visible but never receive a rank.
        </caption>
        <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
          <tr>
            <th className="px-3 py-3 font-semibold">{scoreMode === "static" ? "Status" : "Rank"}</th>
            <SortableHeader label="Model" sortKey="model" sort={sort} onSort={setSort} />
            <SortableHeader label="Run by" sortKey="user" sort={sort} onSort={setSort} />
            <SortableHeader label={<CompositeHeaderLabel scoreMode={scoreMode} season2={season2} />} sortKey="composite" sort={sort} onSort={setSort} />
            {showStaticIndexColumn ? (
              <SortableHeader label={<StaticIndexHeaderLabel />} sortKey={STATIC_INDEX_SORT_KEY} sort={sort} onSort={setSort} />
            ) : null}
            {axisKeys.map((axis) => (
              <SortableHeader
                key={axis}
                label={axis === "tool_use" ? <ToolUseHeaderLabel /> : axisLabel(axis)}
                sortKey={axis}
                sort={sort}
                onSort={setSort}
              />
            ))}
            {showAgenticColumn ? (
              <SortableHeader label={<AgenticHeaderLabel />} sortKey={AGENTIC_SORT_KEY} sort={sort} onSort={setSort} />
            ) : null}
            <SortableHeader label="Runtime" sortKey="runtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Hardware" sortKey="hardware" sort={sort} onSort={setSort} />
            <SortableHeader label="Tokens" sortKey="tokens" sort={sort} onSort={setSort} />
            <SortableHeader label="Time/answer" sortKey="latency" sort={sort} onSort={setSort} />
            <SortableHeader label="Full bench time" sortKey="benchtime" sort={sort} onSort={setSort} />
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <LeaderboardRankedRow
              key={model.slug}
              agentic={agenticBySlug.get(model.slug)}
              axisKeys={axisKeys}
              fineTuneBaseName={fineTuneBaseBySlug.get(model.slug)}
              laneRank={laneRanks.get(model.slug)}
              model={model}
              scoreMode={scoreMode}
              season2={season2}
              showAgenticColumn={showAgenticColumn}
              showStaticIndexColumn={showStaticIndexColumn}
            />
          ))}
          {communityRows.map((row) => (
            <CommunityLeaderboardRow
              key={row.artifactSha256}
              axisKeys={axisKeys}
              row={row}
              showAgenticColumn={showAgenticColumn}
              showStaticIndexColumn={showStaticIndexColumn}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

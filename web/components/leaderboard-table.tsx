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
import type { LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { AGENTIC_SORT_KEY, STATIC_INDEX_SORT_KEY, type SortState } from "@/lib/leaderboard-sort";
import type { AgenticModel } from "@/lib/schemas";
import type { UnifiedLeaderboardRow } from "@/lib/unified-leaderboard";

type LeaderboardTableProps = {
  readonly agenticBySlug: ReadonlyMap<string, AgenticModel>;
  readonly axisKeys: readonly string[];
  readonly fineTuneBaseBySlug: ReadonlyMap<string, string>;
  readonly laneRanks: ReadonlyMap<string, number>;
  readonly rows: readonly UnifiedLeaderboardRow[];
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
  fineTuneBaseBySlug,
  laneRanks,
  rows,
  scoreMode,
  season2,
  setSort,
  showAgenticColumn,
  showStaticIndexColumn,
  sort,
}: LeaderboardTableProps) {
  return (
    <div>
      <p className="border-b border-bench-line px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-bench-accent md:hidden">
        Swipe horizontally for scores and axes →
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-[1280px] border-collapse text-sm">
        <caption className="sr-only">
          Local-bench and community rows share one score-sorted table. Community rows never receive a rank.
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
          {rows.map((entry) => {
            switch (entry.source) {
              case "local-bench":
                return (
                  <LeaderboardRankedRow
                    key={entry.model.slug}
                    agentic={agenticBySlug.get(entry.model.slug)}
                    axisKeys={axisKeys}
                    fineTuneBaseName={fineTuneBaseBySlug.get(entry.model.slug)}
                    laneRank={laneRanks.get(entry.model.slug)}
                    model={entry.model}
                    scoreMode={scoreMode}
                    season2={season2}
                    showAgenticColumn={showAgenticColumn}
                    showStaticIndexColumn={showStaticIndexColumn}
                  />
                );
              case "community":
                return (
                  <CommunityLeaderboardRow
                    key={entry.row.artifactSha256}
                    axisKeys={axisKeys}
                    row={entry.row}
                    showAgenticColumn={showAgenticColumn}
                    showStaticIndexColumn={showStaticIndexColumn}
                  />
                );
              default:
                return assertNever(entry);
            }
          })}
        </tbody>
        </table>
      </div>
    </div>
  );
}

function assertNever(value: never): never {
  throw new Error(`Unhandled leaderboard row: ${String(value)}`);
}

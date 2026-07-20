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
  readonly rows: readonly UnifiedLeaderboardRow[];
  readonly scoreMode: LeaderboardScoreMode;
  readonly season2: boolean;
  readonly setSort: (sort: SortState) => void;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
  readonly sort: SortState;
  readonly vramBySlug: ReadonlyMap<string, number | null>;
};

export function LeaderboardTable({
  agenticBySlug,
  axisKeys,
  fineTuneBaseBySlug,
  rows,
  scoreMode,
  season2,
  setSort,
  showAgenticColumn,
  showStaticIndexColumn,
  sort,
  vramBySlug,
}: LeaderboardTableProps) {
  return (
    <div>
      <p className="border-b border-bench-line px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-bench-accent 2xl:hidden">
        Swipe horizontally for scores and axes →
      </p>
      <div
        tabIndex={0}
        role="region"
        aria-label="Leaderboard table — scrolls horizontally"
        className="overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent"
      >
        <table className="min-w-[1280px] border-collapse text-sm">
        <caption className="sr-only">
          Complete project and community runs share one score-sorted ranked table.
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
                label={season2 && axis === "agentic" ? <ToolUseHeaderLabel /> : axisLabel(axis)}
                sortKey={axis}
                sort={sort}
                onSort={setSort}
              />
            ))}
            {showAgenticColumn ? (
              <SortableHeader label={<AgenticHeaderLabel />} sortKey={AGENTIC_SORT_KEY} sort={sort} onSort={setSort} />
            ) : null}
            <th className="px-3 py-3 font-semibold">VRAM @8k</th>
            <SortableHeader label="Runtime" sortKey="runtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Hardware" sortKey="hardware" sort={sort} onSort={setSort} />
            <SortableHeader
              label={<span title="Median tokens generated per answer (verbosity)">Tokens/answer</span>}
              sortKey="tokens"
              sort={sort}
              onSort={setSort}
            />
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
                    laneRank={entry.rank}
                    model={entry.model}
                    scoreMode={scoreMode}
                    season2={season2}
                    showAgenticColumn={showAgenticColumn}
                    showStaticIndexColumn={showStaticIndexColumn}
                    vramRequiredGb8k={vramBySlug.get(entry.model.slug) ?? null}
                  />
                );
              case "community":
                return (
                  <CommunityLeaderboardRow
                    key={entry.row.artifactSha256}
                    axisKeys={axisKeys}
                    rank={entry.rank}
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
      {axisKeys.includes("agentic") || showAgenticColumn ? (
        <p className="border-t border-bench-line px-3 py-2 text-xs leading-5 text-bench-muted">
          Agentic = AppWorld task-goal completion; 25% weight; near-floor scores compress gaps.
        </p>
      ) : null}
    </div>
  );
}

function assertNever(value: never): never {
  throw new Error(`Unhandled leaderboard row: ${String(value)}`);
}

"use client";

import { useMemo, useState } from "react";
import { BoardScopeHeader } from "@/components/board-scope-header";
import { CommunityFreshness, useLiveCommunityRows } from "@/components/community-live-state";
import { LeaderboardTable } from "@/components/leaderboard-table";
import { axisColumns } from "@/components/leaderboard-table-cells";
import type { CommunityBoardRow } from "@/lib/community-data";
import { type LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { type SortState } from "@/lib/leaderboard-sort";
import type { AgenticModel, IndexModel } from "@/lib/schemas";
import { INDEX_VERSION_V4, isSeason2Board } from "@/lib/scoring-seasons";
import {
  filterUnifiedLeaderboardRows,
  sortUnifiedLeaderboardRows,
  type UnifiedLeaderboardRow,
} from "@/lib/unified-leaderboard";

const EMPTY_AGENTIC: ReadonlyMap<string, AgenticModel> = new Map();
const EMPTY_COMMUNITY: readonly CommunityBoardRow[] = [];
const EMPTY_LINEAGE: ReadonlyMap<string, string> = new Map();

export { sortLeaderboardRows } from "@/lib/leaderboard-sort";
export { filterUnifiedLeaderboardRows, sortUnifiedLeaderboardRows } from "@/lib/unified-leaderboard";

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
  const [family, setFamily] = useState("all");
  const [size, setSize] = useState("all");
  const [quant, setQuant] = useState("all");
  const [ram, setRam] = useState("all");
  const liveCommunity = useLiveCommunityRows(communityRows, scoreMode === "full");
  const axisKeys = useMemo(() => axisColumns(models), [models]);
  const allRows = useMemo(
    () => filterUnifiedLeaderboardRows(models, scoreMode === "full" ? liveCommunity.rows : []),
    [models, liveCommunity.rows, scoreMode],
  );
  const filterOptions = useMemo(() => boardFilterOptions(allRows), [allRows]);
  const visibleRows = useMemo(
    () => sortUnifiedLeaderboardRows(
      allRows.filter((row) => matchesFilters(row, { family, size, quant, ram })),
      sort,
      { agenticBySlug, scoreMode },
    ),
    [allRows, family, size, quant, ram, sort, agenticBySlug, scoreMode],
  );
  const season2 = scoreMode === "full" && isSeason2Board(models, indexVersion);
  const showAgenticColumn = scoreMode === "full" && !season2;
  const showStaticIndexColumn = scoreMode === "full" && !season2;
  const empty = visibleRows.length === 0;

  return (
    <div
      data-testid={scoreMode === "static" ? "static-leaderboard" : "full-leaderboard"}
      className={scoreMode === "static"
        ? "overflow-hidden rounded-lg border border-bench-line/70 bg-bench-panel/45 opacity-90"
        : "overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20"}
    >
      <BoardScopeHeader mode={scoreMode} indexVersion={season2 ? INDEX_VERSION_V4 : indexVersion} />
      {scoreMode === "full" ? (
        <LeaderboardFilters
          family={family}
          options={filterOptions}
          quant={quant}
          ram={ram}
          setFamily={setFamily}
          setQuant={setQuant}
          setRam={setRam}
          setSize={setSize}
          size={size}
          total={allRows.length}
        />
      ) : null}
      {scoreMode === "full" ? (
        <div className="border-b border-bench-line px-3 py-2"><CommunityFreshness state={liveCommunity} /></div>
      ) : null}
      {empty ? (
        <div className="px-4 py-8 text-sm leading-6 text-bench-muted">
          <div className="font-semibold text-bench-text">No rows match this filter</div>
          <div className="mt-1 max-w-3xl">
            Complete runs appear here as soon as they publish. Try a broader family, size, quant, or RAM filter.
          </div>
        </div>
      ) : (
        <LeaderboardTable
          agenticBySlug={agenticBySlug}
          axisKeys={axisKeys}
          fineTuneBaseBySlug={fineTuneBaseBySlug}
          rows={visibleRows}
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

type BoardFilterOptions = {
  readonly families: readonly string[];
  readonly quants: readonly string[];
  readonly rams: readonly string[];
  readonly sizes: readonly string[];
};

function LeaderboardFilters({
  family,
  options,
  quant,
  ram,
  setFamily,
  setQuant,
  setRam,
  setSize,
  size,
  total,
}: {
  readonly family: string;
  readonly options: BoardFilterOptions;
  readonly quant: string;
  readonly ram: string;
  readonly setFamily: (value: string) => void;
  readonly setQuant: (value: string) => void;
  readonly setRam: (value: string) => void;
  readonly setSize: (value: string) => void;
  readonly size: string;
  readonly total: number;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bench-line px-3 py-3">
      <div className="flex flex-wrap gap-2">
        <BoardFilter label="Family" value={family} values={options.families} onChange={setFamily} />
        <BoardFilter label="Model size" value={size} values={options.sizes} onChange={setSize} />
        <BoardFilter label="Quant" value={quant} values={options.quants} onChange={setQuant} />
        <BoardFilter label="RAM" value={ram} values={options.rams} onChange={setRam} />
      </div>
      <p className="font-mono text-xs text-bench-muted">{total} complete ranked run{total === 1 ? "" : "s"}</p>
    </div>
  );
}

function BoardFilter({
  label,
  onChange,
  value,
  values,
}: {
  readonly label: string;
  readonly onChange: (value: string) => void;
  readonly value: string;
  readonly values: readonly string[];
}) {
  return (
    <label className="flex items-center gap-2 rounded border border-bench-line bg-bench-panel-2 px-2 py-1 text-xs text-bench-muted">
      <span>{label}</span>
      <select
        aria-label={`${label} filter`}
        className="bg-transparent font-mono text-bench-text outline-none"
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      >
        <option value="all">All</option>
        {values.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function boardFilterOptions(rows: readonly UnifiedLeaderboardRow[]): BoardFilterOptions {
  return {
    families: unique(rows.map(rowFamily)),
    quants: unique(rows.map(rowQuant)),
    rams: unique(rows.map(rowRam)),
    sizes: unique(rows.map(rowSize)),
  };
}

function matchesFilters(
  row: UnifiedLeaderboardRow,
  filters: { readonly family: string; readonly quant: string; readonly ram: string; readonly size: string },
): boolean {
  return (filters.family === "all" || rowFamily(row) === filters.family)
    && (filters.quant === "all" || rowQuant(row) === filters.quant)
    && (filters.ram === "all" || rowRam(row) === filters.ram)
    && (filters.size === "all" || rowSize(row) === filters.size);
}

function rowFamily(row: UnifiedLeaderboardRow): string | null {
  return row.source === "local-bench" ? row.model.family : row.row.family;
}

function rowQuant(row: UnifiedLeaderboardRow): string | null {
  if (row.source === "community") return row.row.quantLabel;
  return quantFromText(`${row.model.model_label} ${row.model.best_run_id ?? ""}`);
}

function rowRam(row: UnifiedLeaderboardRow): string | null {
  if (row.source === "community") return null;
  const value = row.model.gpu?.vram_gb;
  return value === null || value === undefined ? null : `${value} GB`;
}

function rowSize(row: UnifiedLeaderboardRow): string | null {
  const label = row.source === "local-bench" ? row.model.model_label : row.row.displayName;
  const matches = [...label.matchAll(/(\d+(?:\.\d+)?)\s*b\b/giu)];
  return matches.at(-1)?.[1] === undefined ? null : `${matches.at(-1)?.[1]}B`;
}

function quantFromText(value: string): string | null {
  return /\b(?:UD[-_])?Q\d[A-Z0-9_.-]*/iu.exec(value)?.[0] ?? null;
}

function unique(values: readonly (string | null)[]): readonly string[] {
  return [...new Set(values.filter((value): value is string => value !== null))].sort((left, right) => left.localeCompare(right));
}

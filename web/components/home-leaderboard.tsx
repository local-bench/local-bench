"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { AgenticCell, AgenticHeaderLabel } from "@/components/agentic-column";
import { BoardScopeHeader } from "@/components/board-scope-header";
import { DemoBadge, KindBadge } from "@/components/badges";
import { ConformancePill } from "./conformance-pill";
import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG, isAxisKey } from "@/lib/axis-config";
import { axisLabel, formatDuration, formatGpuShort, formatInteger, formatLatencySeconds } from "@/lib/format";
import { runtimeDisplay, runtimeSortLabel } from "@/lib/runtime-display";
import type { AgenticModel, IndexModel } from "@/lib/schemas";

const AGENTIC_SORT_KEY = "agentic_experimental";
const EMPTY_AGENTIC: ReadonlyMap<string, AgenticModel> = new Map();

type SortKey = string;

type SortDirection = "asc" | "desc";

type SortState = {
  readonly key: SortKey;
  readonly direction: SortDirection;
};

export function HomeLeaderboard({
  models,
  agenticBySlug = EMPTY_AGENTIC,
}: {
  readonly models: readonly IndexModel[];
  readonly agenticBySlug?: ReadonlyMap<string, AgenticModel>;
}) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });
  const axisKeys = useMemo(() => axisColumns(models), [models]);
  const sortedModels = useMemo(() => sortLeaderboardRows(models, sort, agenticBySlug), [models, sort, agenticBySlug]);
  const laneRanks = useMemo(() => buildLaneRanks(models), [models]);

  return (
    <div data-testid="full-leaderboard" className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20">
      <BoardScopeHeader />
      {sortedModels.length === 0 ? (
        <div className="px-4 py-8 text-sm leading-6 text-bench-muted">
          <div className="font-semibold text-bench-text">No ranked rows yet</div>
          <div className="mt-1 max-w-3xl">
            Measured partial profiles are diagnostic and stay on their model pages. A row appears here only after
            Agentic, Knowledge, Instruction, Tool calling, and Coding are all measured in the standard capped-thinking lane.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
        <table className="min-w-[1480px] border-collapse text-sm">
        <caption className="sr-only">
          Rank cells are populated only for ranked Standard rows within the same reasoning lane.
        </caption>
        <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
          <tr>
            <th className="px-3 py-3 font-semibold">Rank</th>
            <SortableHeader label="Model" sortKey="model" sort={sort} onSort={setSort} />
            <SortableHeader label="Kind" sortKey="kind" sort={sort} onSort={setSort} />
            <SortableHeader label={<LocalIntelligenceHeaderLabel />} sortKey="composite" sort={sort} onSort={setSort} />
            {axisKeys.map((axis) => (
              <SortableHeader key={axis} label={axisLabel(axis)} sortKey={axis} sort={sort} onSort={setSort} />
            ))}
            <SortableHeader label={<AgenticHeaderLabel />} sortKey={AGENTIC_SORT_KEY} sort={sort} onSort={setSort} />
            <th className="border-l border-bench-line px-3 py-3 font-semibold">
              <span className="flex flex-col gap-0.5 leading-tight">
                <span>Conformance</span>
                <span className="font-mono text-[10px] normal-case text-bench-muted">Tool calling format gate · not ranked</span>
              </span>
            </th>
            <SortableHeader label="Runtime" sortKey="runtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Hardware" sortKey="hardware" sort={sort} onSort={setSort} />
            <SortableHeader label="Tokens" sortKey="tokens" sort={sort} onSort={setSort} />
            <SortableHeader label="Time/answer" sortKey="latency" sort={sort} onSort={setSort} />
            <SortableHeader label="Full bench time" sortKey="benchtime" sort={sort} onSort={setSort} />
            <SortableHeader label="User" sortKey="user" sort={sort} onSort={setSort} />
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model) => (
            <tr
              key={model.slug}
              className={[
                "border-t border-bench-line/75 align-middle transition-colors hover:bg-white/[0.035]",
                model.kind === "anchor" ? "bg-bench-anchor/[0.025]" : "",
              ].join(" ")}
            >
              <td className="px-3 py-3 font-mono text-bench-muted">
                <RankMarker rank={laneRanks.get(model.slug)} />
              </td>
              <td className="px-3 py-3">
                <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                  {model.model_label}
                </Link>
                {model.demo ? <span className="ml-2"><DemoBadge /></span> : null}
                <div className="text-xs text-bench-muted">{model.family}</div>
              </td>
              <td className="px-3 py-3">
                <KindBadge kind={model.kind} runCount={model.n_runs} />
              </td>
              <td className="px-3 py-3">
                {model.composite === null ? (
                  <NoScoreCell />
                ) : (
                  <ScoreBar axes={model.axes} score={model.composite} tone={model.kind === "anchor" ? "anchor" : "accent"} />
                )}
              </td>
              {axisKeys.map((axisKey) => (
                <td key={axisKey} className="px-3 py-3">
                  <AxisMiniBar score={model.axes[axisKey]} />
                </td>
              ))}
              <td className="px-3 py-3">
                <AgenticCell model={agenticBySlug.get(model.slug)} />
              </td>
              <td className="border-l border-bench-line px-3 py-3">
                <ConformancePill gate={model.conformance_gates?.tc_json_v1} showReason compact />
              </td>
              <td className="px-3 py-3">
                <RuntimeCell runtime={model.runtime} />
              </td>
              <td className="px-3 py-3 font-mono text-xs text-bench-text">{formatGpuShort(model.gpu)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">
                {formatInteger(model.tokens_to_answer_median)}
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(model.latency_s_median ?? null)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatDuration(model.wall_time_seconds ?? null)}</td>
              <td className="px-3 py-3 font-mono text-xs text-bench-muted" title="Top-run submitter — V2 community submissions">{model.submitted_by ?? "—"}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
      )}
    </div>
  );
}

function RankMarker({ rank }: { readonly rank: number | undefined }) {
  if (rank === undefined) {
    return <span className="text-[11px] uppercase">Unranked</span>;
  }
  return formatInteger(rank);
}

function NoScoreCell() {
  return (
    <div className="min-w-[132px]">
      <div className="font-mono text-sm font-semibold text-bench-muted">no data yet</div>
      <div className="mt-1 text-xs text-bench-warn">be the first to benchmark</div>
    </div>
  );
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  readonly label: ReactNode;
  readonly sortKey: SortKey;
  readonly sort: SortState;
  readonly onSort: (sort: SortState) => void;
}) {
  const active = sort.key === sortKey;
  const marker = active ? (sort.direction === "asc" ? "↑" : "↓") : "↕";

  return (
    <th className="px-3 py-3 font-semibold">
      <button
        type="button"
        className="inline-flex items-center gap-1 text-left hover:text-bench-text"
        onClick={() => onSort(nextSort(sort, sortKey))}
      >
        <span>{label}</span>
        <span className={active ? "text-bench-accent" : "text-bench-muted/60"}>{marker}</span>
      </button>
    </th>
  );
}

function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key === key) {
    return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  return { key, direction: key === "model" ? "asc" : "desc" };
}

export function sortLeaderboardRows(
  models: readonly IndexModel[],
  sort: SortState,
  agenticBySlug: ReadonlyMap<string, AgenticModel> = EMPTY_AGENTIC,
): readonly IndexModel[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...models].sort((left, right) => compareRows(left, right, sort.key, agenticBySlug) * direction);
}

function buildLaneRanks(models: readonly IndexModel[]): ReadonlyMap<string, number> {
  const groups = new Map<string, readonly IndexModel[]>();
  for (const model of models) {
    if (!model.ranked) {
      continue;
    }
    const lane = model.lane ?? "n/a";
    const group = groups.get(lane) ?? [];
    groups.set(lane, [...group, model]);
  }

  const ranks = new Map<string, number>();
  for (const group of groups.values()) {
    const rankedGroup = sortLeaderboardRows(group, { key: "composite", direction: "desc" });
    rankedGroup.forEach((model, index) => {
      ranks.set(model.slug, index + 1);
    });
  }
  return ranks;
}

function compareRows(
  left: IndexModel,
  right: IndexModel,
  key: SortKey,
  agenticBySlug: ReadonlyMap<string, AgenticModel>,
): number {
  switch (key) {
    case "model":
      return left.model_label.localeCompare(right.model_label);
    case "kind":
      return left.kind.localeCompare(right.kind);
    case "composite":
      return nullableNumber(left.composite?.point ?? null) - nullableNumber(right.composite?.point ?? null);
    case AGENTIC_SORT_KEY:
      return nullableNumber(agenticBySlug.get(left.slug)?.asr_pct ?? null) - nullableNumber(agenticBySlug.get(right.slug)?.asr_pct ?? null);
    case "tokens":
      return nullableNumber(left.tokens_to_answer_median) - nullableNumber(right.tokens_to_answer_median);
    case "hardware":
      return (left.gpu?.name ?? "").localeCompare(right.gpu?.name ?? "");
    case "runtime":
      return runtimeSortLabel(left.runtime).localeCompare(runtimeSortLabel(right.runtime));
    case "user":
      return (left.submitted_by ?? "").localeCompare(right.submitted_by ?? "");
    case "latency":
      return nullableNumber(left.latency_s_median ?? null) - nullableNumber(right.latency_s_median ?? null);
    case "benchtime":
      return nullableNumber(left.wall_time_seconds ?? null) - nullableNumber(right.wall_time_seconds ?? null);
    default:
      return compareAxis(left, right, key);
  }
}

function RuntimeCell({ runtime }: { readonly runtime: IndexModel["runtime"] }) {
  const display = runtimeDisplay(runtime);
  if (display === null) {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return (
    <span className="flex min-w-[96px] flex-col gap-0.5 leading-tight">
      <span className="font-mono text-xs text-bench-text">{display.label}</span>
      {display.version === null ? null : (
        <span className="font-mono text-[10px] text-bench-muted">{display.version}</span>
      )}
    </span>
  );
}

function LocalIntelligenceHeaderLabel() {
  return (
    <span className="flex flex-col gap-0.5 leading-tight">
      <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
      <span className="font-mono text-[10px] normal-case text-bench-muted">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
    </span>
  );
}

function compareAxis(left: IndexModel, right: IndexModel, axis: string): number {
  return (left.axes[axis]?.point ?? Number.NEGATIVE_INFINITY) - (right.axes[axis]?.point ?? Number.NEGATIVE_INFINITY);
}

function nullableNumber(value: number | null): number {
  return value ?? Number.NEGATIVE_INFINITY;
}

function axisColumns(models: readonly IndexModel[]): readonly string[] {
  const present = new Set<string>();
  for (const model of models) {
    for (const axis of Object.keys(model.axes)) {
      present.add(axis);
    }
  }
  // Agentic is rendered by the dedicated AgenticCell column on the full board, so exclude it
  // from the generic axis columns to avoid a duplicate Agentic column (it IS now in model.axes).
  const configured = AXIS_CONFIG.map((axis) => axis.key).filter((axis) => axis !== "agentic" && present.has(axis));
  const extra = [...present].filter((axis) => !isAxisKey(axis)).sort();
  return [...configured, ...extra];
}

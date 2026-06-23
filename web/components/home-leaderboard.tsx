"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { DemoBadge, KindBadge, TierBadge } from "@/components/badges";
import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG, isAxisKey } from "@/lib/axis-config";
import { axisLabel, formatCost, formatDuration, formatInteger, formatLatencySeconds } from "@/lib/format";
import type { IndexModel } from "@/lib/schemas";

type SortKey = string;

type SortDirection = "asc" | "desc";

type SortState = {
  readonly key: SortKey;
  readonly direction: SortDirection;
};

export function HomeLeaderboard({ models }: { readonly models: readonly IndexModel[] }) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });
  const axisKeys = useMemo(() => axisColumns(models), [models]);
  const sortedModels = useMemo(() => sortRows(models, sort), [models, sort]);
  const laneRanks = useMemo(() => buildLaneRanks(models), [models]);

  return (
    <div data-testid="full-leaderboard" className="overflow-x-auto rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20">
      <table className="min-w-[1120px] border-collapse text-sm">
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
            <SortableHeader label="Tier" sortKey="tier" sort={sort} onSort={setSort} />
            <SortableHeader label="Tokens" sortKey="tokens" sort={sort} onSort={setSort} />
            <SortableHeader label="Time/answer" sortKey="latency" sort={sort} onSort={setSort} />
            <SortableHeader label="Full bench time" sortKey="benchtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Cost" sortKey="cost" sort={sort} onSort={setSort} />
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
                {model.tier === null ? <span className="font-mono text-xs text-bench-muted">not measured</span> : <TierBadge tier={model.tier} />}
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">
                {formatInteger(model.tokens_to_answer_median)}
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(model.latency_s_median ?? null)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatDuration(model.wall_time_seconds ?? null)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatCost(model.est_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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

function sortRows(models: readonly IndexModel[], sort: SortState): readonly IndexModel[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...models].sort((left, right) => compareRows(left, right, sort.key) * direction);
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
    const rankedGroup = sortRows(group, { key: "composite", direction: "desc" });
    rankedGroup.forEach((model, index) => {
      ranks.set(model.slug, index + 1);
    });
  }
  return ranks;
}

function compareRows(left: IndexModel, right: IndexModel, key: SortKey): number {
  switch (key) {
    case "model":
      return left.model_label.localeCompare(right.model_label);
    case "kind":
      return left.kind.localeCompare(right.kind);
    case "composite":
      return nullableNumber(left.composite?.point ?? null) - nullableNumber(right.composite?.point ?? null);
    case "tier":
      return (left.tier ?? "").localeCompare(right.tier ?? "");
    case "tokens":
      return nullableNumber(left.tokens_to_answer_median) - nullableNumber(right.tokens_to_answer_median);
    case "cost":
      return nullableNumber(left.est_cost_usd) - nullableNumber(right.est_cost_usd);
    case "latency":
      return nullableNumber(left.latency_s_median ?? null) - nullableNumber(right.latency_s_median ?? null);
    case "benchtime":
      return nullableNumber(left.wall_time_seconds ?? null) - nullableNumber(right.wall_time_seconds ?? null);
    default:
      return compareAxis(left, right, key);
  }
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
  const configured = AXIS_CONFIG.map((axis) => axis.key).filter((axis) => present.has(axis));
  const extra = [...present].filter((axis) => !isAxisKey(axis)).sort();
  return [...configured, ...extra];
}

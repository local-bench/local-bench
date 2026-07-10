"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { AgenticCell, AgenticHeaderLabel } from "@/components/agentic-column";
import { BoardScopeHeader } from "@/components/board-scope-header";
import { DemoBadge } from "@/components/badges";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { ProvenanceLabels, RunByCell } from "@/components/leaderboard-provenance";
import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG, isAxisKey } from "@/lib/axis-config";
import { axisLabel, formatDuration, formatGpuShort, formatInteger, formatLatencySeconds } from "@/lib/format";
import { scoreForMode, staticIndexStatus, type LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { AGENTIC_SORT_KEY, STATIC_INDEX_SORT_KEY, buildLaneRanks, sortLeaderboardRows, type SortKey, type SortState } from "@/lib/leaderboard-sort";
import { runtimeDisplay } from "@/lib/runtime-display";
import { RuntimeBadge } from "@/components/runtime-badge";
import type { AgenticModel, IndexModel } from "@/lib/schemas";

const EMPTY_AGENTIC: ReadonlyMap<string, AgenticModel> = new Map();

export { sortLeaderboardRows } from "@/lib/leaderboard-sort";

export function HomeLeaderboard({
  models,
  agenticBySlug = EMPTY_AGENTIC,
  scoreMode = "full",
}: {
  readonly models: readonly IndexModel[];
  readonly agenticBySlug?: ReadonlyMap<string, AgenticModel>;
  readonly scoreMode?: LeaderboardScoreMode;
}) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });
  const axisKeys = useMemo(() => axisColumns(models), [models]);
  const sortedModels = useMemo(
    () => sortLeaderboardRows(models, sort, { agenticBySlug, scoreMode }),
    [models, sort, agenticBySlug, scoreMode],
  );
  const laneRanks = useMemo(() => buildLaneRanks(models, scoreMode), [models, scoreMode]);
  const showAgenticColumn = scoreMode === "full";
  const showStaticIndexColumn = false;

  return (
    <div
      data-testid={scoreMode === "static" ? "static-leaderboard" : "full-leaderboard"}
      className={scoreMode === "static"
        ? "overflow-hidden rounded-lg border border-bench-line/70 bg-bench-panel/45 opacity-90"
        : "overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20"}
    >
      <BoardScopeHeader mode={scoreMode} />
      {sortedModels.length === 0 ? (
        <div className="px-4 py-8 text-sm leading-6 text-bench-muted">
          <div className="font-semibold text-bench-text">No ranked rows yet</div>
          <div className="mt-1 max-w-3xl">
            Measured partial profiles are diagnostic and stay on their model pages. A row appears here only after
            the current ranked profile is complete under the bounded-final lane.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
        <table className="min-w-[1280px] border-collapse text-sm">
        <caption className="sr-only">
          Rank cells are populated only for ranked Standard rows within the same reasoning lane.
        </caption>
        <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
          <tr>
            <th className="px-3 py-3 font-semibold">{scoreMode === "static" ? "Status" : "Rank"}</th>
            <SortableHeader label="Model" sortKey="model" sort={sort} onSort={setSort} />
            <SortableHeader label={<CompositeHeaderLabel scoreMode={scoreMode} />} sortKey="composite" sort={sort} onSort={setSort} />
            {showStaticIndexColumn ? (
              <SortableHeader label={<StaticIndexHeaderLabel />} sortKey={STATIC_INDEX_SORT_KEY} sort={sort} onSort={setSort} />
            ) : null}
            {axisKeys.map((axis) => (
              <SortableHeader key={axis} label={axisLabel(axis)} sortKey={axis} sort={sort} onSort={setSort} />
            ))}
            {showAgenticColumn ? (
              <SortableHeader label={<AgenticHeaderLabel />} sortKey={AGENTIC_SORT_KEY} sort={sort} onSort={setSort} />
            ) : null}
            <SortableHeader label="Runtime" sortKey="runtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Hardware" sortKey="hardware" sort={sort} onSort={setSort} />
            <SortableHeader label="Tokens" sortKey="tokens" sort={sort} onSort={setSort} />
            <SortableHeader label="Time/answer" sortKey="latency" sort={sort} onSort={setSort} />
            <SortableHeader label="Full bench time" sortKey="benchtime" sort={sort} onSort={setSort} />
            <SortableHeader label="Run by" sortKey="user" sort={sort} onSort={setSort} />
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model) => {
            const score = scoreForMode(model, scoreMode);
            return (
            <tr
              key={model.slug}
              className="border-t border-bench-line/75 align-middle transition-colors hover:bg-white/[0.035]"
            >
              <td className="px-3 py-3 font-mono text-bench-muted">
                <RankMarker rank={laneRanks.get(model.slug)} provisional={scoreMode === "static"} />
              </td>
              <td className="px-3 py-3">
                <span className="flex items-center gap-2">
                  <FamilyLogoMark modelLabel={model.model_label} size={16} />
                  <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                    {model.model_label}
                  </Link>
                  {model.demo ? <DemoBadge /> : null}
                </span>
                <div className="text-xs text-bench-muted">{model.family}</div>
                <ProvenanceLabels model={model} />
              </td>
              <td className="px-3 py-3">
                {score === null ? (
                  <NoScoreCell />
                ) : (
                  <ScoreBar axes={model.axes} score={score} tone={scoreTone(scoreMode)} rail={scoreMode === "full"} />
                )}
              </td>
              {showStaticIndexColumn ? (
                <td className="px-3 py-3">
                  <StaticIndexCell model={model} />
                </td>
              ) : null}
              {axisKeys.map((axisKey) => (
                <td key={axisKey} className="px-3 py-3">
                  <AxisMiniBar score={model.axes[axisKey]} axis={axisKey} />
                </td>
              ))}
              {showAgenticColumn ? (
                <td className="px-3 py-3">
                  <AgenticCell model={agenticBySlug.get(model.slug)} axisScore={model.axes["agentic"]} />
                </td>
              ) : null}
              <td className="px-3 py-3">
                <RuntimeCell runtime={model.runtime} />
              </td>
              <td className="px-3 py-3 font-mono text-xs text-bench-text">{formatGpuShort(model.gpu)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">
                {formatInteger(model.tokens_to_answer_median)}
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(model.latency_s_median ?? null)}</td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatDuration(model.wall_time_seconds ?? null)}</td>
              <td className="px-3 py-3" title="Who ran this benchmark — local-bench for project-run rows, the submitter for community submissions">
                <RunByCell model={model} />
              </td>
            </tr>
            );
          })}
        </tbody>
        </table>
      </div>
      )}
    </div>
  );
}

function RankMarker({ rank, provisional = false }: { readonly rank: number | undefined; readonly provisional?: boolean }) {
  if (provisional) {
    return <span className="text-[11px] font-semibold uppercase text-bench-warn">Provisional</span>;
  }
  if (rank === undefined) {
    return <span className="text-[11px] uppercase">Unranked</span>;
  }
  return formatInteger(rank);
}

function StaticIndexHeaderLabel() {
  return (
    <span className="flex flex-col gap-0.5 leading-tight">
      <span>Static Index</span>
      <span className="font-mono text-[10px] normal-case text-bench-muted">static-suite-v2 · secondary track</span>
    </span>
  );
}

function StaticIndexCell({ model }: { readonly model: IndexModel }) {
  const score = model.composite_static;
  const status = staticIndexStatus(model);
  if (score === null || score === undefined || status === null) {
    return <span className="font-mono text-xs text-bench-muted">n/a</span>;
  }
  return (
    <div className="min-w-[132px]">
      <ScoreBar score={score} tone="muted" />
      <span className={status === "verified"
        ? "mt-1 inline-flex rounded-full border border-bench-accent/30 bg-bench-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-accent"
        : "mt-1 inline-flex rounded-full border border-bench-warn/40 bg-bench-warn/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-warn"}
      >
        {status}
      </span>
    </div>
  );
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

function RuntimeCell({ runtime }: { readonly runtime: IndexModel["runtime"] }) {
  const display = runtimeDisplay(runtime);
  if (display === null) {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return (
    <span className="flex min-w-[96px] flex-col gap-0.5 leading-tight">
      <RuntimeBadge runtime={runtime} />
      {display.version === null ? null : (
        <span className="font-mono text-[10px] text-bench-muted">{display.version}</span>
      )}
    </span>
  );
}

function CompositeHeaderLabel({ scoreMode }: { readonly scoreMode: LeaderboardScoreMode }) {
  if (scoreMode === "static") {
    return (
      <span className="flex flex-col gap-0.5 leading-tight">
        <span>Static Index</span>
        <span className="font-mono text-[10px] normal-case text-bench-muted">static-suite-v2 · provisional, not a headline rank</span>
      </span>
    );
  }
  return (
    <span className="flex flex-col gap-0.5 leading-tight">
      <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
      <span className="font-mono text-[10px] normal-case text-bench-muted">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
    </span>
  );
}

function scoreTone(scoreMode: LeaderboardScoreMode): "accent" | "muted" {
  return scoreMode === "static" ? "muted" : "accent";
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

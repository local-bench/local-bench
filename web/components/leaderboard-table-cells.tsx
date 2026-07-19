import { type ReactNode } from "react";
import { RuntimeBadge } from "@/components/runtime-badge";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG, isAxisKey } from "@/lib/axis-config";
import { axisLabel, formatInteger, formatScore } from "@/lib/format";
import { scoreForMode, staticIndexStatus, type LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { type SortKey, type SortState } from "@/lib/leaderboard-sort";
import { runtimeDisplay } from "@/lib/runtime-display";
import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import {
  INDEX_VERSION_V4,
  TOOL_USE_FACET_QUALIFIER,
  TOOL_USE_FACETS,
  diagnosticScores,
  displayIndexVersion,
  legacyBridgeScore,
  SEASON_2_INDEX_QUALIFIER,
} from "@/lib/scoring-seasons";
import type { IndexModel } from "@/lib/schemas";
import { publicProtocolLabel } from "@/lib/board-adapter";

export function RankMarker({ rank, provisional = false }: { readonly rank: number | undefined; readonly provisional?: boolean }) {
  if (provisional) {
    return <span className="text-[11px] font-semibold uppercase text-bench-warn">Provisional</span>;
  }
  if (rank === undefined) {
    return <span className="text-[11px] uppercase">Unranked</span>;
  }
  return formatInteger(rank);
}

export function StaticIndexHeaderLabel() {
  return (
    <span className="flex flex-col gap-0.5 leading-tight">
      <span>Static Index</span>
      <span className="font-mono text-[10px] normal-case text-bench-muted">static-suite-v2 · secondary track</span>
    </span>
  );
}

export function StaticIndexCell({ model }: { readonly model: IndexModel }) {
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
        {status === "verified" ? "complete" : status}
      </span>
    </div>
  );
}

export function NoScoreCell() {
  return (
    <div className="min-w-[132px]">
      <div className="font-mono text-sm font-semibold text-bench-muted">no data yet</div>
      <div className="mt-1 text-xs text-bench-warn">be the first to benchmark</div>
    </div>
  );
}

export function CompositeCell({
  model,
  score,
  scoreMode,
}: {
  readonly model: IndexModel;
  readonly score: NonNullable<ReturnType<typeof scoreForMode>>;
  readonly scoreMode: LeaderboardScoreMode;
}) {
  const bridgeScore = legacyBridgeScore(model);
  if (bridgeScore === null) {
    return <ScoreBar axes={model.axes} score={score} tone={scoreTone(scoreMode)} rail={scoreMode === "full"} />;
  }
  return (
    <div className="min-w-[132px]">
      <ScoreBar axes={model.axes} score={score} tone={scoreTone(scoreMode)} rail={scoreMode === "full"} />
      <div className="mt-1 font-mono text-[10px] text-bench-muted">
        index-v3.0 bridge {formatScore(bridgeScore.point)}
      </div>
    </div>
  );
}

export function SeasonBadge({ indexVersion }: { readonly indexVersion: string }) {
  return (
    <span className="rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-bench-accent">
      {publicProtocolLabel(indexVersion)}
    </span>
  );
}

export function ToolUseHeaderLabel() {
  return (
    <span className="flex flex-col gap-0.5 leading-tight">
      <span>{axisLabel("tool_use")}</span>
      <span className="font-mono text-[10px] font-normal normal-case tracking-normal text-bench-muted">
        {TOOL_USE_FACET_QUALIFIER}
      </span>
    </span>
  );
}

export function ToolUseCell({ model }: { readonly model: IndexModel }) {
  const score = model.axes["tool_use"];
  if (score === undefined) {
    return <span className="font-mono text-xs text-bench-muted">n/a</span>;
  }
  const diagnostics = diagnosticScores(model);
  return (
    <div className="min-w-[150px]">
      <AxisMiniBar score={score} axis="tool_use" />
      <details className="mt-1 text-[10px] text-bench-muted">
        <summary className="cursor-pointer font-mono text-bench-accent">facet breakdown</summary>
        <dl className="mt-1 grid gap-1">
          {TOOL_USE_FACETS.map((facet) => {
            const facetScore = score.facets?.[facet.key];
            return (
              <div key={facet.key} className="flex justify-between gap-3">
                <dt>{facet.label} · {Math.round(facet.weight * 100)}%</dt>
                <dd className="font-mono text-bench-text">{facetScore === undefined ? "n/a" : formatScore(facetScore.point)}</dd>
              </div>
            );
          })}
          {diagnostics.length === 0 ? null : (
            <div className="mt-1 border-t border-bench-line/70 pt-1">
              <dt className="font-semibold uppercase text-bench-muted">Diagnostics · unweighted</dt>
              {diagnostics.map((diagnostic) => (
                <div key={diagnostic.key} className="flex justify-between gap-3">
                  <dt>{diagnostic.label}</dt>
                  <dd className="font-mono text-bench-text">{formatScore(diagnostic.score.point)}</dd>
                </div>
              ))}
            </div>
          )}
        </dl>
      </details>
    </div>
  );
}

export function SortableHeader({
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

export function RuntimeCell({ runtime }: { readonly runtime: IndexModel["runtime"] }) {
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

export function CompositeHeaderLabel({ scoreMode, season2 }: { readonly scoreMode: LeaderboardScoreMode; readonly season2: boolean }) {
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
      <span className="font-mono text-[10px] normal-case text-bench-muted">{season2 ? SEASON_2_INDEX_QUALIFIER : LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
    </span>
  );
}

export function axisColumns(models: readonly IndexModel[]): readonly string[] {
  if (models.some((model) => displayIndexVersion(model) === INDEX_VERSION_V4)) {
    return ["tool_use", "knowledge", "instruction", "coding", "math"].filter((axis) =>
      models.some((model) => model.axes[axis] !== undefined),
    );
  }
  const present = new Set<string>();
  for (const model of models) {
    for (const axis of Object.keys(model.axes)) present.add(axis);
  }
  const configured = AXIS_CONFIG.map((axis) => axis.key).filter((axis) => axis !== "agentic" && present.has(axis));
  const extra = [...present].filter((axis) => !isAxisKey(axis)).sort();
  return [...configured, ...extra];
}

function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key === key) {
    return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  return { key, direction: key === "model" ? "asc" : "desc" };
}

function scoreTone(scoreMode: LeaderboardScoreMode): "accent" | "muted" {
  return scoreMode === "static" ? "muted" : "accent";
}

import Link from "next/link";
import { AgenticCell } from "@/components/agentic-column";
import { DemoBadge } from "@/components/badges";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { RunByCell } from "@/components/leaderboard-provenance";
import { AxisMiniBar } from "@/components/score-bar";
import {
  CompositeCell,
  NoScoreCell,
  RankMarker,
  RuntimeCell,
  SeasonBadge,
  StaticIndexCell,
  ToolUseCell,
} from "@/components/leaderboard-table-cells";
import { formatDuration, formatGpuShort, formatInteger, formatLatencySeconds } from "@/lib/format";
import { scoreForMode, type LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { displayIndexVersion } from "@/lib/scoring-seasons";
import type { AgenticModel, IndexModel } from "@/lib/schemas";

type RankedRowProps = {
  readonly agentic: AgenticModel | undefined;
  readonly axisKeys: readonly string[];
  readonly fineTuneBaseName: string | undefined;
  readonly laneRank: number | undefined;
  readonly model: IndexModel;
  readonly scoreMode: LeaderboardScoreMode;
  readonly season2: boolean;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
};

export function LeaderboardRankedRow({
  agentic,
  axisKeys,
  fineTuneBaseName,
  laneRank,
  model,
  scoreMode,
  season2,
  showAgenticColumn,
  showStaticIndexColumn,
}: RankedRowProps) {
  const score = scoreForMode(model, scoreMode);
  return (
    <tr className="border-t border-bench-line/75 align-middle transition-colors hover:bg-white/[0.035]">
      <td className="px-3 py-3 font-mono text-bench-muted">
        <RankMarker rank={laneRank} provisional={scoreMode === "static"} />
      </td>
      <td className="px-3 py-3">
        <span className="flex items-center gap-2">
          <FamilyLogoMark modelLabel={model.model_label} size={16} />
          <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
            {model.model_label}
          </Link>
          {model.demo ? <DemoBadge /> : null}
          {season2 ? <SeasonBadge indexVersion={displayIndexVersion(model)} /> : null}
        </span>
        <div className="text-xs text-bench-muted">{model.family}</div>
        {fineTuneBaseName === undefined ? null : (
          <span className="mt-1 inline-block rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-bench-accent">
            Fine-tune of {fineTuneBaseName}
          </span>
        )}
      </td>
      <td
        className="px-3 py-3"
        title="Who ran this benchmark — local-bench for project-run rows, the submitter for community submissions"
      >
        <RunByCell model={model} />
      </td>
      <td className="px-3 py-3">
        {score === null ? <NoScoreCell /> : <CompositeCell model={model} score={score} scoreMode={scoreMode} />}
      </td>
      {showStaticIndexColumn ? <td className="px-3 py-3"><StaticIndexCell model={model} /></td> : null}
      {axisKeys.map((axisKey) => (
        <td key={axisKey} className="px-3 py-3">
          {axisKey === "tool_use"
            ? <ToolUseCell model={model} />
            : <AxisMiniBar score={model.axes[axisKey]} axis={axisKey} />}
        </td>
      ))}
      {showAgenticColumn ? (
        <td className="px-3 py-3"><AgenticCell model={agentic} axisScore={model.axes["agentic"]} /></td>
      ) : null}
      <td className="px-3 py-3"><RuntimeCell runtime={model.runtime} /></td>
      <td className="px-3 py-3 font-mono text-xs text-bench-text">{formatGpuShort(model.gpu)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatInteger(model.tokens_to_answer_median)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(model.latency_s_median ?? null)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatDuration(model.wall_time_seconds ?? null)}</td>
    </tr>
  );
}

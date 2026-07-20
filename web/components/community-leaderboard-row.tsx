"use client";

import Link from "next/link";
import type { KeyboardEvent } from "react";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { SubmissionIdentity } from "@/components/leaderboard-provenance";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { RuntimeCell, SeasonBadge } from "@/components/leaderboard-table-cells";
import { boardAxisValue, toDisplayScore } from "@/lib/board-adapter";
import { formatDuration, formatGpuShort, formatInteger, formatLatencySeconds, formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { AxisScore, Score } from "@/lib/schemas";
import { SEASON_2_DIAGNOSTICS } from "@/lib/scoring-seasons";

type CommunityRowProps = {
  readonly axisKeys: readonly string[];
  readonly rank: number;
  readonly row: CommunityBoardRow;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
};

export function CommunityLeaderboardRow({
  axisKeys,
  rank,
  row,
  showAgenticColumn,
  showStaticIndexColumn,
}: CommunityRowProps) {
  const displayFamily = row.familyLabel ?? row.catalogFamily ?? row.family;
  const navigate = () => {
    if (row.detailPath !== null) window.location.assign(row.detailPath);
  };
  const openOnEnter = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === "Enter") navigate();
  };
  return (
    <tr
      data-testid={`community-row-${row.submissionId}`}
      data-source="community"
      data-href={row.detailPath ?? undefined}
      tabIndex={row.detailPath === null ? undefined : 0}
      onClick={row.detailPath === null ? undefined : navigate}
      onKeyDown={row.detailPath === null ? undefined : openOnEnter}
      className={`${row.detailPath === null ? "" : "cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent"} border-t border-bench-line/75 bg-white/[0.018] align-middle transition-colors hover:bg-white/[0.035]`}
    >
      <td className="px-3 py-3 font-mono text-bench-muted">{rank}</td>
      <td className="px-3 py-3">
        <span className="flex items-center gap-2">
          <FamilyLogoMark familyName={displayFamily} modelLabel={row.displayName} size={16} />
          {row.detailPath === null ? (
            <span className="font-semibold text-bench-text" title="family detail unavailable for this row">
              {row.displayName}
            </span>
          ) : (
            <Link href={row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">
              {row.displayName}
            </Link>
          )}
          {row.indexVersion === null ? null : <SeasonBadge indexVersion={row.indexVersion} />}
        </span>
        <div className="mt-0.5 font-mono text-xs text-bench-muted">{row.quantLabel ?? "quant unavailable"}</div>
        <div className="text-xs text-bench-muted">{displayFamily ?? row.identityLabel}</div>
        {row.declaredBaseModels?.[0] === undefined ? null : (
          <span className="mt-1 inline-block rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-bench-accent">
            Fine-tune of {row.declaredBaseModels[0]}
          </span>
        )}
      </td>
      <td
        className="px-3 py-3"
        title="Who ran this benchmark — local-bench for project-run rows, the submitter for community submissions"
      >
        <div className="max-w-[180px]">
          <SubmissionIdentity displayName={row.submitterDisplayName} />
        </div>
      </td>
      <td className="px-3 py-3">
        {row.compositeFull === null ? <span className="font-mono text-xs text-bench-muted">—</span> : (
          <div className="min-w-[132px]">
            <ScoreBar score={normalizedScore(row.compositeFull)} />
          <div className="mt-0.5 text-[10px] text-bench-muted">common composite · complete run</div>
          </div>
        )}
      </td>
      {showStaticIndexColumn ? <UnavailableCell /> : null}
      {axisKeys.map((axis) => <CommunityAxisCell key={axis} axis={axis} row={row} />)}
      {showAgenticColumn ? (
        <td className="px-3 py-3">
          <CommunityAxisBar axis="agentic" row={row} />
        </td>
      ) : null}
      <td className="px-3 py-3"><RuntimeCell runtime={row.runtime} /></td>
      <td className="px-3 py-3 font-mono text-xs text-bench-text">
        {row.hardware?.gpu_name === null || row.hardware?.gpu_name === undefined || row.hardware.gpu_name === ""
          ? <span className="text-[10px] text-bench-muted">—</span>
          : formatGpuShort({ name: row.hardware.gpu_name, vram_gb: row.hardware.vram_gb })}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {row.perf?.tokens_to_answer_median === null || row.perf?.tokens_to_answer_median === undefined
          ? <span className="text-[10px] text-bench-muted">—</span>
          : formatInteger(row.perf.tokens_to_answer_median)}
      </td>
      {/* The accepted projection contract does not publish latency yet; keeping this data-driven
          lets the column light up automatically when the optional field reaches the board. */}
      <td className="px-3 py-3 font-mono text-bench-text">
        {formatLatencySeconds(row.perf?.latency_s_median)}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {row.perf?.wall_time_seconds === null || row.perf?.wall_time_seconds === undefined
          ? <span className="text-[10px] text-bench-muted">—</span>
          : formatDuration(row.perf.wall_time_seconds)}
      </td>
    </tr>
  );
}

function CommunityAxisCell({ axis, row }: { readonly axis: string; readonly row: CommunityBoardRow }) {
  return (
    <td className="px-3 py-3">
      {axis === "agentic" ? <CommunityAgenticCell row={row} /> : <CommunityAxisBar axis={axis} row={row} />}
    </td>
  );
}

function CommunityAxisBar({ axis, row }: { readonly axis: string; readonly row: CommunityBoardRow }) {
  const value = boardAxisValue(row.axes ?? {}, axis);
  const score = communityAxisScore(value);
  return (
    <div title={score === undefined ? undefined : `n=${score.n} scored items`}>
      <AxisMiniBar score={score} axis={axis} />
    </div>
  );
}

function CommunityAgenticCell({ row }: { readonly row: CommunityBoardRow }) {
  return (
    <div className="min-w-[220px]">
      <CommunityAxisBar axis="agentic" row={row} />
      <div className="mt-1 font-mono text-[10px] text-bench-muted">AppWorld task-goal completion</div>
      <details className="mt-1 text-[10px] text-bench-muted">
        <summary className="cursor-pointer font-mono text-bench-accent">diagnostics</summary>
        <dl className="mt-1 grid gap-1">
          <dt className="font-semibold uppercase text-bench-muted">Diagnostics · unweighted</dt>
          {SEASON_2_DIAGNOSTICS.map((diagnostic) => (
            <DiagnosticValue
              key={diagnostic.key}
              label={diagnostic.label}
              value={
                boardAxisValue(row.axes ?? {}, diagnostic.key)
                ?? boardAxisValue(row.axes ?? {}, diagnostic.bench)
              }
            />
          ))}
        </dl>
      </details>
    </div>
  );
}

function DiagnosticValue({
  label,
  value,
}: {
  readonly label: string;
  readonly value: ReturnType<typeof boardAxisValue<NonNullable<CommunityBoardRow["axes"]>[string]>>;
}) {
  const score = communityAxisScore(value);
  return (
    <div className="flex justify-between gap-3">
      <dt>{label}</dt>
      <dd className="whitespace-nowrap font-mono text-bench-text">
        {score === undefined ? "not measured" : formatScore(score.point)}
      </dd>
    </div>
  );
}

function UnavailableCell() {
  return (
    <td className="px-3 py-3 font-mono text-[10px] text-bench-muted">
      —
    </td>
  );
}

function normalizedScore(value: number): Score {
  const point = toDisplayScore(value);
  return { point, lo: point, hi: point };
}

function communityAxisScore(
  value: NonNullable<CommunityBoardRow["axes"]>[string] | undefined,
): AxisScore | undefined {
  if (value === undefined || value.status !== "measured" || value.score === null || value.score === undefined || value.n === 0) {
    return undefined;
  }
  const point = toDisplayScore(value.score);
  const lo = toDisplayScore(value.ci?.[0] ?? value.score);
  const hi = toDisplayScore(value.ci?.[1] ?? value.score);
  return {
    point,
    lo,
    hi,
    raw_accuracy: value.score <= 1 ? value.score : value.score / 100,
    n: value.n,
    n_errors: 0,
    n_no_answer: 0,
  };
}

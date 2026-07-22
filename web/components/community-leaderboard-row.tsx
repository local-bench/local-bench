"use client";

import Link from "next/link";
import type { MouseEvent } from "react";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { ProjectRunBadge, SubmissionIdentity } from "@/components/leaderboard-provenance";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { RuntimeCell, SeasonBadge } from "@/components/leaderboard-table-cells";
import { boardAxisValue } from "@/lib/board-adapter";
import { communityAxisScore, communityScore } from "@/lib/community-scores";
import { formatDuration, formatGpuShort, formatInteger, formatLatencySeconds, formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";
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
  const hardware = row.hardware?.gpu_name === null || row.hardware?.gpu_name === undefined || row.hardware.gpu_name === ""
    ? null
    : formatGpuShort({ name: row.hardware.gpu_name, vram_gb: row.hardware.vram_gb });
  const tokensToAnswer = row.perf?.tokens_to_answer_median ?? null;
  const latency = row.perf?.latency_s_median ?? null;
  const wallTime = row.perf?.wall_time_seconds ?? null;
  const navigate = () => {
    if (row.detailPath !== null) window.location.assign(row.detailPath);
  };
  const navigateFromRow = (event: MouseEvent<HTMLTableRowElement>) => {
    if (!shouldNavigateCommunityRow(event.target)) return;
    navigate();
  };
  return (
    <tr
      data-testid={`community-row-${row.submissionId}`}
      data-source="community"
      data-href={row.detailPath ?? undefined}
      onClick={row.detailPath === null ? undefined : navigateFromRow}
      className={`${row.detailPath === null ? "" : "cursor-pointer"} border-t border-bench-line/75 bg-white/[0.018] align-middle transition-colors hover:bg-white/[0.035]`}
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
          {row.origin === "project_anchor" ? (
            <ProjectRunBadge badge={row.badge} origin={row.origin} />
          ) : (
            <SubmissionIdentity displayName={row.submitterDisplayName} />
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        {row.compositeFull === null ? <span className="font-mono text-xs text-bench-muted">—</span> : (
          <div className="min-w-[132px]">
            <ScoreBar score={communityScore(row.compositeFull)} />
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
      <UnavailableCell />
      <td className="px-3 py-3"><RuntimeCell runtime={row.runtime} /></td>
      <td className="px-3 py-3 font-mono text-xs text-bench-text">
        {hardware === null ? <NotCaptured /> : (
          <EnvironmentValue
            backfilled={row.maintainerEnvBackfill?.hardware?.gpu_name === true
              || row.maintainerEnvBackfill?.hardware?.vram_gb === true}
            value={hardware}
          />
        )}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {tokensToAnswer === null ? <NotCaptured /> : (
          <EnvironmentValue
            backfilled={row.maintainerEnvBackfill?.perf?.tokens_to_answer_median === true}
            value={formatInteger(tokensToAnswer)}
          />
        )}
      </td>
      {/* The accepted projection contract does not publish latency yet; keeping this data-driven
          lets the column light up automatically when the optional field reaches the board. */}
      <td className="px-3 py-3 font-mono text-bench-text">
        {latency === null ? <NotCaptured /> : (
          <EnvironmentValue
            backfilled={row.maintainerEnvBackfill?.perf?.latency_s_median === true}
            value={formatLatencySeconds(latency)}
          />
        )}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {wallTime === null ? <NotCaptured /> : (
          <EnvironmentValue
            backfilled={row.maintainerEnvBackfill?.perf?.wall_time_seconds === true}
            value={formatDuration(wallTime)}
          />
        )}
      </td>
    </tr>
  );
}

function EnvironmentValue({ backfilled, value }: { readonly backfilled: boolean; readonly value: string }) {
  if (!backfilled) return value;
  return (
    <span title="maintainer backfill from stored bundle (not submitter-attested)">
      {value} <span className="text-[10px] text-bench-muted">backfill</span>
    </span>
  );
}

function NotCaptured() {
  return <span className="text-[10px] text-bench-muted">not captured</span>;
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
      <AxisMiniBar score={score} axis={axis} showSampleSize />
    </div>
  );
}

export function shouldNavigateCommunityRow(target: EventTarget | null): boolean {
  return target === null || !hasClosest(target) || target.closest("a, summary, details, button") === null;
}

function hasClosest(target: EventTarget): target is EventTarget & { readonly closest: (selector: string) => unknown } {
  return "closest" in target && typeof target.closest === "function";
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

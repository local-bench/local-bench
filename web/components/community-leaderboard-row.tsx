"use client";

import Link from "next/link";
import type { KeyboardEvent } from "react";
import { SubmissionIdentity } from "@/components/leaderboard-provenance";
import { boardAxisValue } from "@/lib/board-adapter";
import { formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";

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
      className={`${row.detailPath === null ? "" : "cursor-pointer hover:bg-white/[0.045] focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent"} border-t-2 border-bench-line-strong bg-white/[0.018] align-middle text-bench-muted transition-colors`}
    >
      <td className="px-3 py-3 font-mono text-bench-muted">{rank}</td>
      <td className="px-3 py-3">
        {row.detailPath === null ? (
          <span className="font-semibold text-bench-text" title="family detail unavailable for this row">
            {row.displayName}
          </span>
        ) : (
          <Link href={row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">
            {row.displayName}
          </Link>
        )}
        <div className="mt-0.5 font-mono text-xs text-bench-muted">{row.quantLabel ?? "quant unavailable"}</div>
        <div className="mt-1 text-[10px] text-bench-muted">{row.family ?? row.identityLabel}</div>
      </td>
      <td className="px-3 py-3">
        <div className="max-w-[180px]">
          <SubmissionIdentity displayName={row.submitterDisplayName} />
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="min-w-[150px]">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-lg font-semibold text-bench-text">
              {row.compositeFull === null ? "unavailable" : formatScore(normalizePercent(row.compositeFull))}
            </span>
          </div>
          <div className="mt-0.5 text-[10px] text-bench-muted">common composite · complete run</div>
        </div>
      </td>
      {showStaticIndexColumn ? <UnavailableCell /> : null}
      {axisKeys.map((axis) => <CommunityAxisCell key={axis} axis={axis} row={row} />)}
      {showAgenticColumn ? (
        <td className="px-3 py-3">
          <CommunityAxisValue axis="agentic" row={row} />
        </td>
      ) : null}
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
    </tr>
  );
}

function CommunityAxisCell({ axis, row }: { readonly axis: string; readonly row: CommunityBoardRow }) {
  return <td className="px-3 py-3"><CommunityAxisValue axis={axis} row={row} /></td>;
}

function CommunityAxisValue({ axis, row }: { readonly axis: string; readonly row: CommunityBoardRow }) {
  const value = boardAxisValue(row.axes ?? {}, axis);
  if (value === undefined) return <span className="font-mono text-[10px] text-bench-muted">—</span>;
  if (value.status !== "measured" || value.score === null || value.score === undefined) {
    return <span className="font-mono text-[10px] text-bench-muted">{value.status.replace("_", " ")}</span>;
  }
  return (
    <div>
      <div className="min-w-[96px] font-mono text-sm font-semibold text-bench-text">
        {formatScore(normalizePercent(value.score))}
      </div>
      <div className="mt-1 font-mono text-[10px] text-bench-muted">n={value.n}</div>
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

function normalizePercent(value: number): number {
  return value <= 1 ? value * 100 : value;
}

"use client";

import Link from "next/link";
import type { KeyboardEvent } from "react";
import { AttributionChip } from "@/components/leaderboard-provenance";
import { formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";

type CommunityRowProps = {
  readonly axisKeys: readonly string[];
  readonly row: CommunityBoardRow;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
};

export function CommunityLeaderboardRow({
  axisKeys,
  row,
  showAgenticColumn,
  showStaticIndexColumn,
}: CommunityRowProps) {
  const navigate = () => window.location.assign(row.detailPath);
  const openOnEnter = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === "Enter") navigate();
  };
  return (
    <tr
      data-testid={`community-row-${row.submissionId}`}
      data-source="community"
      data-href={row.detailPath}
      tabIndex={0}
      onClick={navigate}
      onKeyDown={openOnEnter}
      className="cursor-pointer border-t-2 border-bench-line-strong bg-white/[0.018] align-middle text-bench-muted transition-colors hover:bg-white/[0.045] focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent"
    >
      <td className="px-3 py-3 font-mono text-bench-muted" title="Community rows are not ranked">—</td>
      <td className="px-3 py-3">
        <Link href={row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">
          {row.displayName}
        </Link>
        <div className="mt-0.5 font-mono text-xs text-bench-muted">{row.quantLabel ?? "quant unavailable"}</div>
        <div className="mt-1 text-[10px] uppercase text-bench-muted">{row.identityLabel}</div>
      </td>
      <td className="px-3 py-3">
        <div className="min-w-[150px]">
          <span className="font-mono text-lg font-semibold text-bench-text">
            {row.partialComposite === null ? "unavailable" : formatScore(row.partialComposite * 100)}
          </span>
          <div className="mt-0.5 text-[10px] text-bench-muted">partial over measured headline axes</div>
          <div className="mt-1 font-mono text-[10px] text-bench-muted">
            measured {percentage(row.measuredHeadlineWeight)} · missing {percentage(row.missingHeadlineWeight)}
          </div>
        </div>
      </td>
      {showStaticIndexColumn ? <UnavailableCell /> : null}
      {axisKeys.map((axis) => <UnavailableCell key={axis} axis />)}
      {showAgenticColumn ? <UnavailableCell axis /> : null}
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
      <UnavailableCell />
      <td className="px-3 py-3">
        <AttributionChip source="community" />
        <div className="mt-1 max-w-[150px] text-[10px] leading-4 text-bench-muted">not independently verified</div>
      </td>
    </tr>
  );
}

function UnavailableCell({ axis = false }: { readonly axis?: boolean }) {
  return (
    <td className="px-3 py-3 font-mono text-[10px] text-bench-muted" title={axis ? "Per-axis values are not included in community publication v2" : undefined}>
      {axis ? "not published in v2" : "—"}
    </td>
  );
}

function percentage(value: number | null): string {
  return value === null ? "unavailable" : `${(value * 100).toFixed(1)}%`;
}

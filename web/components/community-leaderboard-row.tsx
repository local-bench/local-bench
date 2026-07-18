"use client";

import Link from "next/link";
import type { KeyboardEvent } from "react";
import {
  AgenticProvenanceChip,
  AttributionChip,
  TrustTierChip,
} from "@/components/leaderboard-provenance";
import { formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";

type CommunityRowProps = {
  readonly axisKeys: readonly string[];
  readonly row: CommunityBoardRow;
  readonly showAgenticColumn: boolean;
  readonly showStaticIndexColumn: boolean;
};

const HEADLINE_AXIS_COUNT = 6;

export function CommunityLeaderboardRow({
  axisKeys,
  row,
  showAgenticColumn,
  showStaticIndexColumn,
}: CommunityRowProps) {
  const measuredAxes = measuredAxisCount(row);
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
      <td className="px-3 py-3" title="Community rows are not ranked">
        <TrustTierChip trustLabel={row.trust?.trust_label ?? "community_self_submitted"} />
      </td>
      <td className="px-3 py-3">
        {row.detailPath === null ? (
          <span className="font-semibold text-bench-text" title="detail page publishes with the next site deploy">
            {row.displayName}
          </span>
        ) : (
          <Link href={row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">
            {row.displayName}
          </Link>
        )}
        <div className="mt-0.5 font-mono text-xs text-bench-muted">{row.quantLabel ?? "quant unavailable"}</div>
        <div className="mt-1 text-[10px] uppercase text-bench-muted">{row.identityLabel}</div>
      </td>
      <td className="px-3 py-3">
        <AttributionChip source="community" />
        <div className="mt-1 max-w-[150px] text-[10px] leading-4 text-bench-muted">
          {submitterLabel(row) ?? "not independently verified"}
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="min-w-[150px]">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-lg font-semibold text-bench-text">
              {row.partialComposite === null ? "unavailable" : formatScore(row.partialComposite * 100)}
            </span>
            {measuredAxes === null ? null : (
              <span className="font-mono text-[10px] font-semibold text-bench-accent">
                {measuredAxes}/{HEADLINE_AXIS_COUNT} axes
              </span>
            )}
          </div>
          <div className="mt-0.5 text-[10px] text-bench-muted">partial over measured headline axes</div>
          {measuredAxes === null ? (
            <div className="mt-1 font-mono text-[10px] text-bench-muted">
              measured {percentage(row.measuredHeadlineWeight)} · missing {percentage(row.missingHeadlineWeight)}
            </div>
          ) : null}
        </div>
      </td>
      {showStaticIndexColumn ? <UnavailableCell /> : null}
      {axisKeys.map((axis) => <CommunityAxisCell key={axis} axis={axis} row={row} />)}
      {showAgenticColumn ? (
        <td className="px-3 py-3">
          {row.trust === null || row.trust === undefined
            ? <span className="font-mono text-[10px] text-bench-muted">not published in v2</span>
            : <AgenticProvenanceChip value={row.trust.agentic_provenance} />}
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
  const value = row.axes?.[axis];
  if (value === undefined) return <UnavailableCell axis />;
  if (axis === "coding" && value.status !== "measured") {
    return <td className="px-3 py-3 font-mono text-[10px] text-bench-warn">pending verification</td>;
  }
  if (value.status !== "measured" || value.score === null) {
    return <td className="px-3 py-3 font-mono text-[10px] text-bench-muted">{value.status.replace("_", " ")}</td>;
  }
  return (
    <td className="px-3 py-3">
      <div className="min-w-[96px] font-mono text-sm font-semibold text-bench-text">
        {formatScore(value.score * 100)}
      </div>
      <div className="mt-1 font-mono text-[10px] text-bench-muted">n={value.n}</div>
    </td>
  );
}

function submitterLabel(row: CommunityBoardRow): string | null {
  if (row.submitterDisplayName !== null && row.submitterDisplayName !== undefined) {
    return `submitted by ${row.submitterDisplayName}`;
  }
  if (row.submitterKeyFingerprint !== null && row.submitterKeyFingerprint !== undefined) {
    return `submitted by key:${row.submitterKeyFingerprint}`;
  }
  return null;
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

function measuredAxisCount(row: CommunityBoardRow): number | null {
  const axes = Object.values(row.axes ?? {});
  if (axes.length === 0) return null;
  return axes.filter((axis) => axis.status === "measured").length;
}

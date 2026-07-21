import Link from "next/link";
import { AgenticProvenanceChip } from "@/components/leaderboard-provenance";
import { RuntimeCell } from "@/components/leaderboard-table-cells";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { boardAxisValue } from "@/lib/board-adapter";
import { communityAxisScore, communityDisplayAxes, communityScore } from "@/lib/community-scores";
import type { CommunityBoardRow } from "@/lib/community-data";
import { formatCompactNumber } from "@/lib/format";

type CommunityVariantTableRowProps = {
  readonly axisKeys: readonly string[];
  readonly hasPerf: boolean;
  readonly rank: number | null;
  readonly row: CommunityBoardRow;
};

export function CommunityVariantTableRow({
  axisKeys,
  hasPerf,
  rank,
  row,
}: CommunityVariantTableRowProps) {
  const complete = row.headlineComplete && row.compositeFull !== null;
  return (
    <tr
      data-source="community"
      data-testid={`community-variant-${row.submissionId}`}
      className="border-t border-bench-line/75 bg-bench-panel-2/35 align-middle hover:bg-white/[0.035]"
    >
      <td className="px-3 py-3 font-mono text-bench-muted">{rank ?? "—"}</td>
      <td className="px-3 py-3">
        <div className="flex min-w-[240px] flex-col gap-1">
          {row.detailPath === null ? (
            <span className="font-semibold text-bench-text">{row.displayName}</span>
          ) : (
            <Link href={row.detailPath} className="font-semibold text-bench-accent hover:underline">
              {row.displayName}
            </Link>
          )}
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-semibold text-bench-text">{row.quantLabel ?? "n/a"}</span>
            <AgenticProvenanceChip value="self-reported" />
            {complete ? null : (
              <span className="inline-flex rounded border border-bench-muted/40 bg-bench-muted/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bench-muted">
                partial headline
              </span>
            )}
          </span>
        </div>
      </td>
      <td className="px-3 py-3">
        {complete ? (
          <ScoreBar axes={communityDisplayAxes(row)} score={communityScore(row.compositeFull)} />
        ) : (
          <>
            <span className="font-mono text-sm text-bench-muted">—</span>
            <div className="mt-1 font-mono text-[10px] uppercase text-bench-warn-soft">
              diagnostic partial — no comparable Index
            </div>
          </>
        )}
      </td>
      {axisKeys.map((axis) => (
        <td key={axis} className="px-3 py-3">
          <AxisMiniBar score={communityAxisScore(boardAxisValue(row.axes ?? {}, axis))} axis={axis} />
        </td>
      ))}
      <td className="px-3 py-3 font-mono text-bench-muted">—</td>
      <td className="px-3 py-3 font-mono text-bench-text">n/a</td>
      {hasPerf ? <td className="px-3 py-3" /> : null}
      {hasPerf ? (
        <td className="px-3 py-3 font-mono text-bench-text">
          {row.perf?.decode_tps === null || row.perf?.decode_tps === undefined
            ? ""
            : formatCompactNumber(row.perf.decode_tps)}
        </td>
      ) : null}
      <td className="px-3 py-3 font-mono text-bench-muted">—</td>
      <td className="px-3 py-3 font-mono text-bench-muted">—</td>
      <td className="px-3 py-3"><RuntimeCell runtime={row.runtime} /></td>
      <td className="px-3 py-3">
        {row.detailPath === null ? (
          <span className="font-mono text-xs text-bench-muted">—</span>
        ) : (
          <Link href={row.detailPath} className="font-mono text-xs text-bench-accent hover:underline">
            detail
          </Link>
        )}
      </td>
    </tr>
  );
}

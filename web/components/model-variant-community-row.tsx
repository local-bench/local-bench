import Link from "next/link";
import { AgenticProvenanceChip, ProjectRunBadge } from "@/components/leaderboard-provenance";
import { RuntimeCell } from "@/components/leaderboard-table-cells";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { boardAxisValue } from "@/lib/board-adapter";
import { communityAxisScore, communityDisplayAxes, communityScore } from "@/lib/community-scores";
import type { CommunityArtifactDetail } from "@/lib/community-artifact-details";
import type { CommunityBoardRow } from "@/lib/community-data";
import { formatCompactNumber, formatGb } from "@/lib/format";
import { findMinimumVramTier } from "@/lib/rig-match";

type CommunityVariantTableRowProps = {
  readonly artifactDetail?: CommunityArtifactDetail | undefined;
  readonly axisKeys: readonly string[];
  readonly hasPerf: boolean;
  readonly rank: number | null;
  readonly row: CommunityBoardRow;
};

// Same tier ladder as the catalog rows' quant-decision fit, but sourced from the
// catalog artifact's @8k estimate — community projections don't carry rig-match runs.
function communityFitTier(vramGb8k: number | null | undefined): string {
  if (vramGb8k === null || vramGb8k === undefined) return "n/a";
  const tier = findMinimumVramTier(vramGb8k);
  return tier === null ? ">512 GB" : `${tier} GB`;
}

export function CommunityVariantTableRow({
  artifactDetail,
  axisKeys,
  hasPerf,
  rank,
  row,
}: CommunityVariantTableRowProps) {
  const complete = row.headlineComplete && row.compositeFull !== null;
  const displayName = artifactDetail?.modelLabel ?? row.displayName;
  const showDeclaredName = displayName !== row.displayName;
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
            <span className="font-semibold text-bench-text">{displayName}</span>
          ) : (
            <Link href={row.detailPath} className="font-semibold text-bench-accent hover:underline">
              {displayName}
            </Link>
          )}
          {showDeclaredName ? (
            <span className="font-mono text-[11px] text-bench-muted">declared as {row.displayName}</span>
          ) : null}
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-semibold text-bench-text">{row.quantLabel ?? "n/a"}</span>
            {row.origin === "project_anchor" ? (
              <ProjectRunBadge badge={row.badge} origin={row.origin} />
            ) : (
              <AgenticProvenanceChip value="self-reported" />
            )}
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
      <td className={`px-3 py-3 font-mono ${artifactDetail?.vramGb8k == null ? "text-bench-muted" : "text-bench-text"}`}>
        {artifactDetail?.vramGb8k == null ? "—" : formatGb(artifactDetail.vramGb8k)}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{communityFitTier(artifactDetail?.vramGb8k)}</td>
      {hasPerf ? <td className="px-3 py-3" /> : null}
      {hasPerf ? (
        <td className="px-3 py-3 font-mono text-bench-text">
          {row.perf?.decode_tps === null || row.perf?.decode_tps === undefined
            ? ""
            : formatCompactNumber(row.perf.decode_tps)}
        </td>
      ) : null}
      <td className="px-3 py-3 font-mono text-bench-muted">—</td>
      <td className={`px-3 py-3 font-mono ${artifactDetail?.fileGb == null ? "text-bench-muted" : "text-bench-text"}`}>
        {artifactDetail?.fileGb == null ? "—" : formatGb(artifactDetail.fileGb)}
      </td>
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

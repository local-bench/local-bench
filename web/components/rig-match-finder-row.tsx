import Link from "next/link";
import { DemoBadge } from "@/components/badges";
import { formatCi, formatCompactNumber, formatGb, formatScore } from "@/lib/format";
import { formatContextLength, type RigMatch, type RigMatchVerdict } from "@/lib/rig-match";

export function FinderRow({ match, rank }: { readonly match: RigMatch; readonly rank: number }) {
  return (
    <tr className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
      <td className="px-3 py-3 font-mono text-bench-muted">{rank}</td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/model/${match.modelSlug}`} className="font-semibold text-bench-text hover:text-bench-accent">
            {match.modelLabel}
          </Link>
          {match.demo ? <DemoBadge /> : null}
        </div>
        <div className="text-xs text-bench-muted">{match.family}</div>
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{match.quantLabel ?? "n/a"}</td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {match.score === null ? (
          <span className="text-bench-muted">no data yet</span>
        ) : (
          <>
            {formatScore(match.score.point)} <span className="text-bench-muted">{formatCi(match.score)}</span>
          </>
        )}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {match.score === null ? <span className="text-bench-warn">benchmark bounty</span> : `${Math.round(match.frontierGapPercent)}% of top anchor`}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">
        <div>{formatGb(match.vramEstimate.effectiveRequiredGb)}</div>
        <div className="text-xs text-bench-muted">
          fits at ~{formatContextLength(match.vramEstimate.contextTokens)} ctx ·{" "}
          {formatGb(match.vramEstimate.kvCacheGb + match.vramEstimate.overheadGb)} reserved
        </div>
        <div className="text-xs text-bench-muted">weights {formatGb(match.vramEstimate.weightsGb)}</div>
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(match.tokS)}</td>
      <td className="px-3 py-3">
        <VerdictChip verdict={match.verdict} />
      </td>
    </tr>
  );
}

function VerdictChip({ verdict }: { readonly verdict: RigMatchVerdict }) {
  const styles: Record<RigMatchVerdict, string> = {
    "best-under-budget": "border-bench-better/45 bg-bench-better/10 text-bench-better",
    "needs-replication": "border-bench-warn/45 bg-bench-warn/10 text-bench-warn",
    "not-enough-data": "border-bench-muted/45 bg-white/[0.03] text-bench-muted",
    "statistical-tie": "border-bench-tied/45 bg-white/[0.03] text-bench-tied",
  };
  return (
    <span className={["inline-flex rounded border px-2 py-1 text-[11px] font-semibold uppercase", styles[verdict]].join(" ")}>
      {verdict.replace(/-/g, " ")}
    </span>
  );
}

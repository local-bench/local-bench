import Link from "next/link";
import { BoardScopeHeader } from "@/components/board-scope-header";
import { familyStyle } from "@/lib/family-color";
import { formatCi, formatCompactNumber, formatDuration, formatGb, formatLatencySeconds, formatScore } from "@/lib/format";
import { findMinimumVramTier } from "@/lib/rig-match";
import type { BestVariantPoint } from "@/lib/best-variant";

// The scatter's companion: the same best-variant-per-model points as a precise, scannable list.
// Colour swatches tie each row back to its dot, so the crowded top of the chart stays legible here.
export function BestVariantTable({ points }: { readonly points: readonly BestVariantPoint[] }) {
  if (points.length === 0) {
    return null;
  }
  const rows = [...points].sort((left, right) => right.score.point - left.score.point);
  return (
    <section
      data-testid="best-variant-table"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <BoardScopeHeader />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
        <caption className="sr-only">Best variant per model, ranked by Local Intelligence Index</caption>
        <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
          <tr>
            <th className="w-10 px-3 py-3">#</th>
            <th className="px-3 py-3">Model</th>
            <th className="px-3 py-3">Local Intelligence Index</th>
            <th className="px-3 py-3">VRAM to run</th>
            <th className="px-3 py-3">tok/s</th>
            <th className="px-3 py-3">Time/answer</th>
            <th className="px-3 py-3">Full bench time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((point, index) => {
            const style = familyStyle(point.family);
            const tier = findMinimumVramTier(point.effectiveVramGb);
            return (
              <tr key={point.runId} className="border-t border-bench-line/75 align-middle transition-colors hover:bg-white/[0.035]">
                <td className="px-3 py-3 font-mono text-bench-muted">{index + 1}</td>
                <td className="px-3 py-3">
                  <span className="flex flex-wrap items-center gap-2">
                    <span
                      aria-hidden
                      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: style.color }}
                    />
                    <Link href={`/model/${point.modelSlug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                      {point.modelLabel}
                    </Link>
                    {point.quantLabel ? <span className="font-mono text-xs text-bench-muted">{point.quantLabel}</span> : null}
                    {point.isFrontier ? (
                      <span className="rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bench-accent">
                        frontier
                      </span>
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-3 font-mono text-bench-text">
                  {formatScore(point.score.point)} <span className="text-bench-muted">{formatCi(point.score)}</span>
                </td>
                <td className="px-3 py-3 font-mono text-bench-text">
                  ~{formatGb(point.effectiveVramGb)}{" "}
                  <span className="text-xs text-bench-muted">{tier === null ? ">512 GB" : `fits ${tier} GB`}</span>
                </td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(point.tokS)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatLatencySeconds(point.latencySMedian)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatDuration(point.wallTimeSeconds)}</td>
              </tr>
            );
          })}
        </tbody>
        </table>
      </div>
    </section>
  );
}

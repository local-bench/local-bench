import Link from "next/link";
import { AxisMiniBar, IndexContributionRail } from "@/components/score-bar";
import { axisColor } from "@/lib/axis-config";
import { familyStyle } from "@/lib/family-color";
import { formatCi, formatCompactNumber, formatDuration, formatGb, formatScore } from "@/lib/format";
import { findMinimumVramTier } from "@/lib/rig-match";
import type { BestVariantPoint } from "@/lib/best-variant";
import type { AxisScore } from "@/lib/schemas";

export function BestVariantTable({ points }: { readonly points: readonly BestVariantPoint[] }) {
  if (points.length === 0) {
    return (
      <section
        data-testid="best-variant-table"
        className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
      >
        <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Leaderboard summary</p>
          <h2 className="mt-1 text-2xl font-semibold text-bench-text">No ranked variants yet</h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">
            Partial benchmark profiles are available on model pages, but the Local Intelligence Index ranks only rows
            with the current ranked profile complete under the bounded-final lane.
          </p>
        </div>
      </section>
    );
  }
  const rows = [...points].sort((left, right) => right.score.point - left.score.point);
  const showFrontierChips = rows.length >= 3;
  const top = rows[0];
  const second = rows[1];
  const tied = top !== undefined && second !== undefined && top.score.lo <= second.score.hi;
  return (
    <section
      data-testid="best-variant-table"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Leaderboard summary</p>
        <h2 className="mt-1 text-2xl font-semibold text-bench-text">Best ranked variant per model</h2>
        <p className="mt-1 text-xs leading-5 text-bench-muted">
          Best local model variants ranked so far, by the Local Intelligence Index
          (
          <span className="font-mono">
            0.40 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool + 0.15 Coding + 0.05 Math
          </span>
          ).
          See the full leaderboard for every quant, hardware, and run provenance.
        </p>
        <p className="mt-1 font-mono text-[11px] text-bench-muted-2">
          {rows.length} ranked model{rows.length === 1 ? "" : "s"} so far
          {tied ? "; the top two are statistically tied within uncertainty" : ""}.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1080px] border-collapse text-sm">
          <caption className="sr-only">Best complete current-index variant per model, ranked by the Local Intelligence Index</caption>
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="w-10 px-3 py-3">#</th>
              <th className="px-3 py-3">Model</th>
              <th className="px-3 py-3">Local Intelligence Index v3.0</th>
              <th className="px-3 py-3">VRAM / fits</th>
              <th className="px-3 py-3"><AxisDot axis="agentic" />Agentic 40%</th>
              <th className="px-3 py-3"><AxisDot axis="knowledge" />Knowledge 15%</th>
              <th className="px-3 py-3"><AxisDot axis="instruction" />Instruction 15%</th>
              <th className="px-3 py-3"><AxisDot axis="tool_calling" />Tool calling 10%</th>
              <th className="px-3 py-3"><AxisDot axis="coding" />Coding 15%</th>
              <th className="px-3 py-3"><AxisDot axis="math" />Math 5%</th>
              <th className="px-3 py-3">tok/s</th>
              <th className="px-3 py-3">Bench time</th>
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
                      {showFrontierChips && point.isFrontier ? (
                        <span
                          className="rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bench-accent"
                          title="No ranked model is both smaller and higher-scoring — the best pick at this VRAM budget (size-vs-score Pareto frontier; see Methodology). Not a capability tier."
                        >
                          best at its size
                        </span>
                      ) : null}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <div className="min-w-[150px]">
                      <div className="font-mono text-bench-text">
                        {formatScore(point.score.point)} <span className="text-bench-muted">{formatCi(point.score)}</span>
                      </div>
                      <IndexContributionRail axes={point.axes} className="mt-1.5 h-1.5 w-full max-w-[170px]" />
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-bench-text">
                    ~{formatGb(point.effectiveVramGb)}{" "}
                    <span className="text-xs text-bench-muted">{tier === null ? ">512 GB" : `fits ${tier} GB`}</span>
                  </td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["agentic"]} axis="agentic" /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["knowledge"]} axis="knowledge" /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["instruction"]} axis="instruction" /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["tool_calling"]} axis="tool_calling" /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["coding"]} axis="coding" /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["math"]} axis="math" /></td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(point.tokS)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-bench-muted">{formatDuration(point.wallTimeSeconds)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-bench-line px-3 py-2 text-xs leading-5 text-bench-muted">
        Tool calling uses tc_json_v1 plaintext tool-call tasks. Coding ranks only after BigCodeBench-Hard project
        re-execution in the hardened sandbox; legacy lcb output-prediction data is diagnostic only.
      </p>
    </section>
  );
}

function AxisDot({ axis }: { readonly axis: string }) {
  return (
    <span
      aria-hidden
      className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle"
      style={{ backgroundColor: axisColor(axis) }}
    />
  );
}

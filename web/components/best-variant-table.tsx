import Link from "next/link";
import { AxisMiniBar } from "@/components/score-bar";
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
          <h2 className="mt-1 text-lg font-semibold text-bench-text">No ranked variants yet</h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">
            Partial benchmark profiles are available on model pages, but the Local Intelligence Index ranks only rows
            with Agentic, Knowledge, Instruction, Tool calling, and Coding all measured under the standard capped-thinking lane.
          </p>
        </div>
      </section>
    );
  }
  const rows = [...points].sort((left, right) => right.score.point - left.score.point);
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
        <p className="mt-1 text-xs leading-5 text-bench-muted">
          Best local model variants ranked so far, by the Local Intelligence Index
          (<span className="font-mono">0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool + 0.10 Coding</span>).
          See the full leaderboard for every quant, hardware, and run provenance.
        </p>
        <p className="mt-1 font-mono text-[11px] text-bench-muted-2">
          {rows.length} ranked model{rows.length === 1 ? "" : "s"} so far
          {tied ? "; the top two are statistically tied within uncertainty" : ""}.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1080px] border-collapse text-sm">
          <caption className="sr-only">Best complete five-axis variant per model, ranked by the Local Intelligence Index</caption>
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="w-10 px-3 py-3">#</th>
              <th className="px-3 py-3">Model</th>
              <th className="px-3 py-3">Local Intelligence Index v2.1</th>
              <th className="px-3 py-3">VRAM / fits</th>
              <th className="px-3 py-3">Agentic 50%</th>
              <th className="px-3 py-3">Knowledge 15%</th>
              <th className="px-3 py-3">Instruction 15%</th>
              <th className="px-3 py-3">Tool calling 10%</th>
              <th className="px-3 py-3">Coding 10%</th>
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
                      {point.isFrontier ? (
                        <span className="rounded border border-bench-accent/40 bg-bench-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bench-accent">
                          frontier
                        </span>
                      ) : null}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <div className="min-w-[150px]">
                      <div className="font-mono text-bench-text">
                        {formatScore(point.score.point)} <span className="text-bench-muted">{formatCi(point.score)}</span>
                      </div>
                      <ContributionRail axes={point.axes} />
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-bench-text">
                    ~{formatGb(point.effectiveVramGb)}{" "}
                    <span className="text-xs text-bench-muted">{tier === null ? ">512 GB" : `fits ${tier} GB`}</span>
                  </td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["agentic"]} /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["knowledge"]} /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["instruction"]} /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["tool_calling"]} /></td>
                  <td className="px-3 py-3"><AxisMiniBar score={point.axes["coding"]} /></td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(point.tokS)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-bench-muted">{formatDuration(point.wallTimeSeconds)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-bench-line px-3 py-2 text-xs leading-5 text-bench-muted">
        Tool calling uses tc_json_v1 plaintext tool-call tasks. Coding uses the lightweight LiveCodeBench output-prediction proxy in standard runs; BigCodeBench-Hard stays opt-in.
      </p>
    </section>
  );
}

function ContributionRail({ axes }: { readonly axes: Readonly<Record<string, AxisScore>> }) {
  const a = (axes["agentic"]?.point ?? 0) * 0.5;
  const k = (axes["knowledge"]?.point ?? 0) * 0.15;
  const i = (axes["instruction"]?.point ?? 0) * 0.15;
  const t = (axes["tool_calling"]?.point ?? 0) * 0.1;
  const c = (axes["coding"]?.point ?? 0) * 0.1;
  const total = a + k + i + t + c;
  return (
    <div
      className="mt-1.5 flex h-1.5 w-full max-w-[170px] overflow-hidden rounded-full bg-white/10"
      title={`Agentic ${a.toFixed(1)} + Knowledge ${k.toFixed(1)} + Instruction ${i.toFixed(1)} + Tool ${t.toFixed(1)} + Coding ${c.toFixed(1)} = ${total.toFixed(1)}`}
    >
      <div className="h-full bg-bench-accent" style={{ width: `${a}%` }} />
      <div className="h-full bg-bench-accent/60" style={{ width: `${k}%` }} />
      <div className="h-full bg-bench-accent/35" style={{ width: `${i}%` }} />
      <div className="h-full bg-bench-anchor/60" style={{ width: `${t}%` }} />
      <div className="h-full bg-bench-mixed" style={{ width: `${c}%` }} />
    </div>
  );
}

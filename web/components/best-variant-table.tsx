import Link from "next/link";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
  SEASON_2_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { AxisMiniBar, IndexContributionRail } from "@/components/score-bar";
import { axisColor } from "@/lib/axis-config";
import { INDEX_AXIS_WEIGHTS, SEASON_2_AXIS_WEIGHTS } from "@/lib/axis-contributions";
import { familyStyle } from "@/lib/family-color";
import { orgLogoForModelLabel } from "@/lib/family-logo";
import { axisLabel, formatCi, formatCompactNumber, formatDuration, formatGb, formatScore } from "@/lib/format";
import { findMinimumVramTier } from "@/lib/rig-match";
import { TOOL_USE_FACET_QUALIFIER } from "@/lib/scoring-seasons";
import type { BestVariantPoint } from "@/lib/best-variant";
import type { AxisScore } from "@/lib/schemas";

// Display order of the per-axis columns, one list per season. Weights render from the same
// constants the contribution rail uses, so the header percentages can never drift from scoring.
const SEASON_1_AXIS_KEYS = ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"] as const;
const SEASON_2_AXIS_KEYS = ["tool_use", "knowledge", "instruction", "coding", "math"] as const;

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
            Partial benchmark profiles are available on model pages; the Local Intelligence Index ranks only complete
            measured profiles.
          </p>
        </div>
      </section>
    );
  }
  const rows = [...points].sort((left, right) => right.score.point - left.score.point);
  // Same season feature-detection rule as indexQualifierForAxes / indexContributions: only
  // season-2 scoring produces the tool_use macro-axis, so any row carrying it means the board
  // (and therefore this summary) is index-v4.0.
  const season2 = rows.some((row) => row.axes["tool_use"] !== undefined);
  const axisKeys: readonly string[] = season2 ? SEASON_2_AXIS_KEYS : SEASON_1_AXIS_KEYS;
  const axisWeights: Readonly<Record<string, number>> = season2 ? SEASON_2_AXIS_WEIGHTS : INDEX_AXIS_WEIGHTS;
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
          Each model&apos;s best ranked variant, scored by the Local Intelligence Index — axis weights are in the
          column headers.{" "}
          <Link href="/leaderboard" className="text-bench-accent underline hover:text-bench-text">
            See the full leaderboard
          </Link>{" "}
          for every quant, hardware, and run provenance.
        </p>
        <p className="mt-1 font-mono text-[11px] text-bench-muted-2">
          {rows.length} ranked model{rows.length === 1 ? "" : "s"} so far
          {tied ? "; the top two are statistically tied within uncertainty" : ""}.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1080px] border-collapse text-sm">
          <caption className="sr-only">Best ranked variant per model, by the Local Intelligence Index</caption>
          <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
            <tr>
              <th className="w-10 px-3 py-3">#</th>
              <th className="px-3 py-3">Model</th>
              <th className="px-3 py-3">
                <span className="flex flex-col gap-0.5 leading-tight">
                  <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
                  <span className="font-mono text-[10px] normal-case text-bench-muted">
                    {season2 ? SEASON_2_INDEX_QUALIFIER : LOCAL_INTELLIGENCE_INDEX_QUALIFIER}
                  </span>
                </span>
              </th>
              <th className="px-3 py-3">VRAM / fits</th>
              {axisKeys.map((axis) => (
                <th key={axis} className="px-3 py-3">
                  <AxisDot axis={axis} />
                  {axisLabel(axis)} {Math.round((axisWeights[axis] ?? 0) * 100)}%
                  {axis === "tool_use" ? (
                    <span className="block font-mono text-[10px] font-normal normal-case tracking-normal text-bench-muted">
                      {TOOL_USE_FACET_QUALIFIER}
                    </span>
                  ) : null}
                </th>
              ))}
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
                      {orgLogoForModelLabel(point.modelLabel) !== null ? (
                        <FamilyLogoMark modelLabel={point.modelLabel} size={16} />
                      ) : (
                        <span
                          aria-hidden
                          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: style.color }}
                        />
                      )}
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
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3"><AxisMiniBar score={point.axes[axis]} axis={axis} /></td>
                  ))}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(point.tokS)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-bench-muted">{formatDuration(point.wallTimeSeconds)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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

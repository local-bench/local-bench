import Link from "next/link";
import { ConformancePill } from "@/components/conformance-pill";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG, presentAxes } from "@/lib/axis-config";
import { axisLabel, formatCompactNumber, formatGb } from "@/lib/format";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { getQuantDecisionRows, type QuantDecisionRow } from "@/lib/quant-decision";
import { DEFAULT_CONTEXT_TOKENS, formatContextLength } from "@/lib/rig-match";
import { runtimeDisplay } from "@/lib/runtime-display";
import type { ModelData } from "@/lib/data";
import type { ConformanceGate } from "@/lib/schemas";

type VariantRun = ModelData["runs"][number];

export function ModelVariantBoard({
  model,
  formatGate,
}: {
  readonly model: ModelData;
  // tc_json tool-call format gate for this model's measured runs — shown with the variant
  // measurements it qualifies (it is a diagnostic, not a score, so it lives here rather than
  // as its own page section).
  readonly formatGate?: ConformanceGate | undefined;
}) {
  // Measured rows split by lane: only headline-lane (current-index) runs may show a Local
  // Intelligence Index bar. Runs measured under retired lanes carry composites from an earlier
  // index version — they render in a separate diagnostics table without an Index column so the
  // page never invites a cross-index comparison.
  const isCurrentIndexRun = (run: VariantRun): boolean =>
    run.score_status !== "measured" || run.lane === HEADLINE_LANE;
  const currentRuns = model.runs.filter(isCurrentIndexRun);
  const legacy = [...model.runs]
    .filter((run) => run.score_status === "measured" && run.lane !== HEADLINE_LANE)
    .sort((left, right) => (right.composite?.point ?? 0) - (left.composite?.point ?? 0));
  const axisKeys = variantAxisColumns(currentRuns);
  const decisionByQuant = new Map<string, QuantDecisionRow>(
    getQuantDecisionRows({ ...model, runs: currentRuns }, DEFAULT_CONTEXT_TOKENS).rows.map((row) => [
      row.quantLabel,
      row,
    ]),
  );
  const ranked = currentRuns
    .filter((run) => run.ranked && run.composite !== null)
    .sort((left, right) => (right.composite?.point ?? 0) - (left.composite?.point ?? 0));
  const partial = currentRuns.filter((run) => !run.ranked && run.score_status === "measured");
  const pending = currentRuns.filter((run) => run.composite === null && run.score_status !== "measured");
  const hasPerf = currentRuns.some((run) => run.perf !== undefined);

  return (
    <>
    <section data-testid="model-variant-board" className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel">
      <div className="border-b border-bench-line px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-bench-text">Variant profiles</h2>
          {formatGate === undefined ? null : (
            <span className="flex items-center gap-2 text-xs text-bench-muted">
              <span className="font-mono">tc_json_v1 format gate</span>
              <ConformancePill gate={formatGate} showReason compact />
            </span>
          )}
        </div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
            Complete rows are ordered by {LOCAL_INTELLIGENCE_INDEX_NAME}{" "}
            (<span className="font-mono text-xs">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>). Partial rows show measured
            diagnostic axes but do not receive a rank until the current ranked profile is complete. The VRAM/Fits columns (
            {formatContextLength(DEFAULT_CONTEXT_TOKENS)} context) tell you what your card needs.
          </p>
      </div>
      <div className="overflow-x-auto">
        <table data-testid="model-variant-table" className="min-w-[1360px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3 font-semibold">Rank</th>
              <th className="px-3 py-3 font-semibold">Variant</th>
              <th className="px-3 py-3 font-semibold">Runtime</th>
              <th className="px-3 py-3 font-semibold">
                <span className="flex flex-col gap-0.5 leading-tight">
                  <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
                  <span className="font-mono text-[10px] normal-case text-bench-muted">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
                </span>
              </th>
              {axisKeys.map((axis) => (
                <th key={axis} className="px-3 py-3 font-semibold">
                  {axisLabel(axis)}
                </th>
              ))}
              <th className="px-3 py-3 font-semibold">VRAM @8k</th>
              <th className="px-3 py-3 font-semibold">Fits</th>
              <th className="px-3 py-3 font-semibold">tok/s</th>
              {hasPerf ? <th className="px-3 py-3 font-semibold">decode tok/s</th> : null}
              <th className="px-3 py-3 font-semibold">Footprint</th>
              <th className="px-3 py-3 font-semibold">Run</th>
            </tr>
          </thead>
          <tbody>
            {ranked.length + partial.length + pending.length === 0 ? (
              <tr className="border-t border-bench-line/75">
                <td colSpan={9 + axisKeys.length + (hasPerf ? 1 : 0)} className="px-3 py-5 text-sm text-bench-muted">
                  No current-index measurements yet.{" "}
                  <Link
                    href={`/submit?model=${encodeURIComponent(model.slug)}`}
                    className="font-mono text-xs text-bench-warn hover:underline"
                  >
                    benchmark it
                  </Link>
                </td>
              </tr>
            ) : null}
            {ranked.map((run, index) => {
              const decision = run.quant_label === null ? undefined : decisionByQuant.get(run.quant_label);
              return (
                <tr key={run.run_id ?? run.quant_label ?? index} className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
                  <td className="px-3 py-3 font-mono text-bench-muted">{index + 1}</td>
                  <td className="px-3 py-3">
                    <span className="font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</span>
                    <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                      {index === 0 ? (
                        <Badge tone="accent" title="Best measured variant — the row shown on the full leaderboard">best</Badge>
                      ) : null}
                      {decision?.isSweetSpot ? (
                        <Badge tone="better" title="Smallest variant that still holds the best variant's quality">sweet spot</Badge>
                      ) : null}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <RuntimeCell run={run} />
                  </td>
                  <td className="px-3 py-3">
                    {run.composite === null ? (
                      <span className="text-bench-muted">no data</span>
                    ) : (
                      <ScoreBar axes={run.axes} score={run.composite} />
                    )}
                  </td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      <AxisMiniBar score={run.axes[axis]} axis={axis} />
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatFitTier(decision)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                  {hasPerf ? <td className="px-3 py-3 font-mono text-bench-text">{formatDecodeTps(run)}</td> : null}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3">
                    {run.run_id === null ? (
                      <span className="font-mono text-xs text-bench-muted">—</span>
                    ) : (
                      <Link href={`/run/${run.run_id}`} className="font-mono text-xs text-bench-accent hover:underline">
                        receipt
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
            {partial.map((run, index) => (
              <tr key={`partial-${run.quant_label ?? index}`} className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
                <td className="px-3 py-3 font-mono text-bench-muted">—</td>
                <td className="px-3 py-3">
                  <span className="font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</span>
                  <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                    <Badge tone="muted" title="Partial measurement; missing one or more headline modules">partial headline</Badge>
                  </span>
                </td>
                <td className="px-3 py-3">
                  <RuntimeCell run={run} />
                </td>
                <td className="px-3 py-3">
                  {run.composite === null ? (
                    <span className="font-mono text-xs text-bench-muted">not measured</span>
                  ) : (
                    <div>
                      <ScoreBar axes={run.axes} score={run.composite} />
                      <div className="mt-1 font-mono text-[10px] uppercase text-bench-warn-soft">unranked diagnostic</div>
                    </div>
                  )}
                </td>
                {axisKeys.map((axis) => (
                  <td key={axis} className="px-3 py-3">
                    <AxisMiniBar score={run.axes[axis]} axis={axis} />
                  </td>
                ))}
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">n/a</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                {hasPerf ? <td className="px-3 py-3 font-mono text-bench-text">{formatDecodeTps(run)}</td> : null}
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3">
                  {run.run_id === null ? (
                    <span className="font-mono text-xs text-bench-muted">—</span>
                  ) : (
                    <Link href={`/run/${run.run_id}`} className="font-mono text-xs text-bench-accent hover:underline">
                      receipt
                    </Link>
                  )}
                </td>
              </tr>
            ))}
            {pending.map((run, index) => {
              const decision = run.quant_label === null ? undefined : decisionByQuant.get(run.quant_label);
              return (
                <tr key={`pending-${run.quant_label ?? index}`} className="border-t border-bench-line/75 align-middle text-bench-muted">
                  <td className="px-3 py-3 font-mono">—</td>
                  <td className="px-3 py-3 font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</td>
                  <td className="px-3 py-3">
                    <RuntimeCell run={run} />
                  </td>
                  <td className="px-3 py-3">no run yet</td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      —
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono">{formatFitTier(decision)}</td>
                  <td className="px-3 py-3">—</td>
                  {hasPerf ? <td className="px-3 py-3" /> : null}
                  <td className="px-3 py-3 font-mono">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3">
                    <Link href={`/submit?model=${encodeURIComponent(model.slug)}`} className="font-mono text-xs text-bench-warn hover:underline">
                      benchmark it
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
    <LegacyDiagnostics runs={legacy} />
    </>
  );
}

// Runs measured under retired lanes (earlier index versions). Axis readings stay visible as
// diagnostics, but there is deliberately no Local Intelligence Index column here: those
// composites are on a retired scale and must not sit next to current-index numbers.
function LegacyDiagnostics({ runs }: { readonly runs: readonly VariantRun[] }) {
  if (runs.length === 0) {
    return null;
  }
  return (
    <section
      data-testid="model-legacy-diagnostics"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Previous-index diagnostics</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          These runs were measured under a retired lane on an earlier version of the Index, so their scores are not
          comparable to the current {LOCAL_INTELLIGENCE_INDEX_NAME} and are excluded from ranks, charts, and
          comparisons. Axis readings and hardware costs remain useful as diagnostics until each variant is re-run on
          the current lane.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table data-testid="model-legacy-table" className="min-w-[980px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3 font-semibold">Variant</th>
              <th className="px-3 py-3 font-semibold">Lane</th>
              <th className="px-3 py-3 font-semibold">Runtime</th>
              <th className="px-3 py-3 font-semibold">Measured axes (retired scale)</th>
              <th className="px-3 py-3 font-semibold">VRAM @8k</th>
              <th className="px-3 py-3 font-semibold">tok/s</th>
              <th className="px-3 py-3 font-semibold">Footprint</th>
              <th className="px-3 py-3 font-semibold">Run</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run, index) => (
              <tr
                key={`legacy-${run.run_id ?? run.quant_label ?? index}`}
                className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]"
              >
                <td className="px-3 py-3">
                  <span className="font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</span>
                </td>
                <td className="px-3 py-3">
                  <span className="inline-flex rounded border border-bench-line bg-white/[0.03] px-2 py-1 font-mono text-[11px] uppercase text-bench-muted">
                    {run.lane ?? "n/a"}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <RuntimeCell run={run} />
                </td>
                <td className="px-3 py-3">
                  <LegacyAxisPoints run={run} />
                </td>
                <td className="px-3 py-3 font-mono text-bench-text">
                  {formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}
                </td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3">
                  {run.run_id === null ? (
                    <span className="font-mono text-xs text-bench-muted">—</span>
                  ) : (
                    <Link href={`/run/${run.run_id}`} className="font-mono text-xs text-bench-accent hover:underline">
                      receipt
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LegacyAxisPoints({ run }: { readonly run: VariantRun }) {
  const entries = presentAxes(run.axes);
  if (entries.length === 0) {
    return <span className="font-mono text-xs text-bench-muted">n/a</span>;
  }
  return (
    <div className="flex flex-wrap gap-3">
      {entries.map(([axis, score]) => (
        <div key={axis} className="min-w-[112px]">
          <div className="mb-1 font-mono text-[10px] uppercase text-bench-muted">{axisLabel(axis)}</div>
          <AxisMiniBar score={score} axis={axis} />
        </div>
      ))}
    </div>
  );
}

function Badge({ tone, title, children }: { readonly tone: "accent" | "better" | "muted"; readonly title: string; readonly children: string }) {
  const cls =
    tone === "better"
      ? "border-bench-better/45 bg-bench-better/10 text-bench-better"
      : tone === "muted"
        ? "border-bench-muted/40 bg-bench-muted/10 text-bench-muted"
        : "border-bench-accent/45 bg-bench-accent/10 text-bench-accent";
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${cls}`} title={title}>
      {children}
    </span>
  );
}

function RuntimeCell({ run }: { readonly run: VariantRun }) {
  const display = runtimeDisplay(run.runtime);
  if (display === null) {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return (
    <span className="flex min-w-[96px] flex-col gap-0.5 leading-tight">
      <span className="font-mono text-xs text-bench-text">{display.label}</span>
      {display.version === null ? null : (
        <span className="font-mono text-[10px] text-bench-muted">{display.version}</span>
      )}
    </span>
  );
}

function formatDecodeTps(run: VariantRun): string {
  return run.perf?.decode_tps === null || run.perf?.decode_tps === undefined ? "" : formatCompactNumber(run.perf.decode_tps);
}

// "Fits" = the smallest GPU VRAM tier a variant runs on at the displayed context (from the
// quant-decision rig-match). Null tier = larger than the biggest modelled card.
function formatFitTier(decision: QuantDecisionRow | undefined): string {
  if (decision === undefined || decision.vramEstimate === null) {
    return "n/a";
  }
  return decision.fitTierGb === null ? ">512 GB" : `${decision.fitTierGb} GB`;
}

// Headline + present axes (n > 0) for this model's runs, in canonical display order.
function variantAxisColumns(runs: readonly VariantRun[]): readonly string[] {
  const present = new Set<string>();
  for (const run of runs) {
    for (const [axis, score] of Object.entries(run.axes)) {
      if (score !== undefined && score.n > 0) {
        present.add(axis);
      }
    }
  }
  return AXIS_CONFIG.map((axis) => axis.key).filter((key) => present.has(key));
}

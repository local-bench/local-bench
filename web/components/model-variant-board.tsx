import Link from "next/link";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { ConformancePill } from "./conformance-pill";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { axisLabel, formatCompactNumber, formatGb } from "@/lib/format";
import { getQuantDecisionRows, type QuantDecisionRow } from "@/lib/quant-decision";
import { DEFAULT_CONTEXT_TOKENS, formatContextLength } from "@/lib/rig-match";
import type { ModelData } from "@/lib/data";

type VariantRun = ModelData["runs"][number];

// Per-model leaderboard: this model's quant/distill variants ranked DESCENDING by the Local
// Intelligence Index — the same presentation language as the full board, scoped to one model.
// Ranks by composite.point; variants with no run yet sink to the bottom as benchmark bounties.
// Rank 1 = best quality (the row the full leaderboard shows). The "sweet spot" badge marks the
// smallest variant that still holds ~the best variant's quality (from getQuantDecisionRows), so
// the board both RANKS and RECOMMENDS. New quants/distills appear automatically once their run is
// added to data_sources.json and the data is rebuilt — nothing here is hand-wired.
export function ModelVariantBoard({ model }: { readonly model: ModelData }) {
  const axisKeys = variantAxisColumns(model.runs);
  const decisionByQuant = new Map<string, QuantDecisionRow>(
    getQuantDecisionRows(model, DEFAULT_CONTEXT_TOKENS).rows.map((row) => [row.quantLabel, row]),
  );
  const ranked = [...model.runs]
    .filter((run) => run.composite !== null)
    .sort((left, right) => (right.composite?.point ?? 0) - (left.composite?.point ?? 0));
  const partial = model.runs.filter((run) => run.composite === null && run.score_status === "measured");
  const pending = model.runs.filter((run) => run.composite === null && run.score_status !== "measured");

  return (
    <section data-testid="model-variant-board" className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel">
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Variants ranked</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Every measured quant and distill of {model.model_label}, ordered by {LOCAL_INTELLIGENCE_INDEX_NAME}{" "}
          (<span className="font-mono text-xs">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>). Quality stays ~flat across the
          top quants, then falls off — the <span className="text-bench-better">sweet spot</span> is the smallest variant
          that still holds quality, and the VRAM/Fits columns ({formatContextLength(DEFAULT_CONTEXT_TOKENS)} context) tell you
          what your card needs.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table data-testid="model-variant-table" className="min-w-[1260px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3 font-semibold">Rank</th>
              <th className="px-3 py-3 font-semibold">Variant</th>
              <th className="px-3 py-3 font-semibold">
                <span className="flex flex-col gap-0.5 leading-tight">
                  <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
                  <span className="font-mono text-[10px] normal-case text-bench-muted">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
                </span>
              </th>
              <th className="px-3 py-3 font-semibold">JSON gate</th>
              {axisKeys.map((axis) => (
                <th key={axis} className="px-3 py-3 font-semibold">
                  {axisLabel(axis)}
                </th>
              ))}
              <th className="px-3 py-3 font-semibold">VRAM @8k</th>
              <th className="px-3 py-3 font-semibold">Fits</th>
              <th className="px-3 py-3 font-semibold">tok/s</th>
              <th className="px-3 py-3 font-semibold">Footprint</th>
              <th className="px-3 py-3 font-semibold">Run</th>
            </tr>
          </thead>
          <tbody>
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
                    {run.composite === null ? (
                      <span className="text-bench-muted">no data</span>
                    ) : (
                      <ScoreBar axes={run.axes} score={run.composite} />
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <ConformancePill gate={run.conformance_gates?.tc_json_v1} compact />
                  </td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      <AxisMiniBar score={run.axes[axis]} />
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatFitTier(decision)}</td>
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
              );
            })}
            {partial.map((run, index) => (
              <tr key={`partial-${run.quant_label ?? index}`} className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
                <td className="px-3 py-3 font-mono text-bench-muted">—</td>
                <td className="px-3 py-3">
                  <span className="font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</span>
                  <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                    <Badge tone="muted" title="Agentic-only measurement; no Core Text Knowledge/Instruction run">agentic-only (no Core Text)</Badge>
                  </span>
                </td>
                <td className="px-3 py-3">
                  <span className="font-mono text-xs text-bench-muted">not measured</span>
                </td>
                <td className="px-3 py-3">
                  <ConformancePill gate={run.conformance_gates?.tc_json_v1} compact />
                </td>
                {axisKeys.map((axis) => (
                  <td key={axis} className="px-3 py-3">
                    <AxisMiniBar score={run.axes[axis]} />
                  </td>
                ))}
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">n/a</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3">
                  <span className="font-mono text-xs text-bench-muted">—</span>
                </td>
              </tr>
            ))}
            {pending.map((run, index) => {
              const decision = run.quant_label === null ? undefined : decisionByQuant.get(run.quant_label);
              return (
                <tr key={`pending-${run.quant_label ?? index}`} className="border-t border-bench-line/75 align-middle text-bench-muted">
                  <td className="px-3 py-3 font-mono">—</td>
                  <td className="px-3 py-3 font-mono font-semibold text-bench-text">{run.quant_label ?? "n/a"}</td>
                  <td className="px-3 py-3">no run yet</td>
                  <td className="px-3 py-3">
                    <ConformancePill gate={undefined} compact />
                  </td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      —
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono">{formatFitTier(decision)}</td>
                  <td className="px-3 py-3">—</td>
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

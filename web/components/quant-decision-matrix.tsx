import Link from "next/link";
import { DemoBadge } from "@/components/badges";
import { formatCi, formatCompactNumber, formatGb, formatScore } from "@/lib/format";
import { DEFAULT_CONTEXT_TOKENS, formatContextLength } from "@/lib/rig-match";
import {
  getQuantDecisionRows,
  type QuantDecisionInputModel,
  type QuantDecisionRow,
} from "@/lib/quant-decision";
import type { Score } from "@/lib/schemas";

export function QuantDecisionMatrix({ model }: { readonly model: QuantDecisionInputModel }) {
  const decision = getQuantDecisionRows(model, DEFAULT_CONTEXT_TOKENS);

  return (
    <section data-testid="quant-decision-matrix" className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Which quant should I run?</p>
          <h2 className="mt-2 text-2xl font-semibold text-bench-text">Decision matrix</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
            Effective VRAM uses {formatContextLength(DEFAULT_CONTEXT_TOKENS)} context with KV cache and runtime headroom.
          </p>
        </div>
        <Link
          href="/compare"
          className="rounded border border-bench-accent/45 bg-bench-accent/10 px-3 py-2 text-sm font-semibold text-bench-accent hover:bg-bench-accent/15"
        >
          Compare configs
        </Link>
      </div>

      <CoverageCards
        baselineQuantLabel={decision.baselineQuantLabel}
        hasFp16Baseline={decision.hasFp16Baseline}
        missingQuantLabels={decision.missingQuantLabels}
        modelLabel={model.model_label}
      />

      <div className="mt-5 overflow-x-auto rounded border border-bench-line bg-bench-panel-2/70">
        <table className="min-w-[980px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3">Quant</th>
              <th className="px-3 py-3">Quality</th>
              <th className="px-3 py-3">Δ vs {decision.baselineQuantLabel ?? "baseline"}</th>
              <th className="px-3 py-3">Effective VRAM</th>
              <th className="px-3 py-3">Fits</th>
              <th className="px-3 py-3">tok/s</th>
              <th className="px-3 py-3">Call</th>
            </tr>
          </thead>
          <tbody>
            {decision.rows.map((row) => (
              <QuantDecisionTableRow key={row.quantLabel} modelSlug={model.slug} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CoverageCards({
  baselineQuantLabel,
  hasFp16Baseline,
  missingQuantLabels,
  modelLabel,
}: {
  readonly baselineQuantLabel: string | null;
  readonly hasFp16Baseline: boolean;
  readonly missingQuantLabels: readonly string[];
  readonly modelLabel: string;
}) {
  if (hasFp16Baseline && missingQuantLabels.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      {!hasFp16Baseline ? (
        <div className="rounded border border-bench-warn/35 bg-bench-warn/10 p-3 text-sm leading-6 text-bench-warn">
          FP16 baseline missing for {modelLabel}; using {baselineQuantLabel ?? "the highest measured quant"} as the delta
          baseline until an FP16 run lands.
        </div>
      ) : null}
      {missingQuantLabels.length > 0 ? (
        <div className="rounded border border-bench-line bg-bench-panel-2 p-3 text-sm leading-6 text-bench-muted">
          Coverage gaps: <span className="font-mono text-bench-text">{missingQuantLabels.join(", ")}</span>
        </div>
      ) : null}
    </div>
  );
}

function QuantDecisionTableRow({ modelSlug, row }: { readonly modelSlug: string; readonly row: QuantDecisionRow }) {
  return (
    <tr className="border-t border-bench-line/75 align-top hover:bg-white/[0.035]">
      <td className="px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono font-semibold text-bench-text">{row.quantLabel}</span>
          {row.run?.demo ? <DemoBadge /> : null}
        </div>
        {row.run ? (
          <Link href={`/run/${row.run.run_id}`} className="mt-1 block font-mono text-xs text-bench-accent hover:underline">
            {row.run.run_id}
          </Link>
        ) : (
          <span className="mt-1 block text-xs text-bench-muted">not measured</span>
        )}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{row.run ? scoreWithCi(row.run.composite) : "coverage needed"}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatDelta(row.deltaVsBaseline)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {row.vramEstimate ? (
          <>
            <div>{formatGb(row.vramEstimate.effectiveRequiredGb)}</div>
            <div className="text-xs text-bench-muted">weights {formatGb(row.vramEstimate.weightsGb)}</div>
          </>
        ) : (
          "n/a"
        )}
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatFitTier(row)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(row.run?.tok_s)}</td>
      <td className="px-3 py-3">
        {row.isSweetSpot ? (
          <span className="inline-flex rounded border border-bench-better/45 bg-bench-better/10 px-2 py-1 text-[11px] font-semibold uppercase text-bench-better">
            Sweet spot
          </span>
        ) : row.isBaseline ? (
          <span className="inline-flex rounded border border-bench-line bg-white/[0.03] px-2 py-1 text-[11px] font-semibold uppercase text-bench-muted">
            Baseline
          </span>
        ) : row.run ? (
          <Link href={`/compare?left=${encodeURIComponent(row.run.run_id)}`} className="text-sm font-semibold text-bench-accent hover:underline">
            Compare
          </Link>
        ) : (
          <Link href={`/submit?model=${encodeURIComponent(modelSlug)}`} className="text-sm font-semibold text-bench-warn hover:underline">
            Submit
          </Link>
        )}
      </td>
    </tr>
  );
}

function scoreWithCi(score: Score): string {
  return `${formatScore(score.point)} ${formatCi(score)}`;
}

function formatDelta(score: Score | null): string {
  if (score === null) {
    return "needs baseline";
  }
  if (score.point === 0) {
    return "baseline";
  }
  const sign = score.point > 0 ? "+" : "";
  return `${sign}${formatScore(score.point)} ${formatCi(score)}`;
}

function formatFitTier(row: QuantDecisionRow): string {
  if (row.vramEstimate === null) {
    return "n/a";
  }
  return row.fitTierGb === null ? ">512 GB" : `${row.fitTierGb} GB`;
}

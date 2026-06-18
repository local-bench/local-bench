import Link from "next/link";
import { KindBadge, LaneBadge, TierBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ModelAxisProfile } from "@/components/model-axis-profile";
import { ModelScatter } from "@/components/model-scatter";
import { QuantDecisionMatrix } from "@/components/quant-decision-matrix";
import { AXES, getModelPageData, getModelStaticParams } from "@/lib/data";
import {
  axisLabel,
  formatCi,
  formatCompactNumber,
  formatCost,
  formatGb,
  formatHardware,
  formatInteger,
  formatScore,
} from "@/lib/format";

export const dynamicParams = false;

type PageProps = {
  readonly params: Promise<{
    readonly slug: string;
  }>;
};

export async function generateStaticParams(): Promise<{ slug: string }[]> {
  return [...(await getModelStaticParams())];
}

export default async function ModelPage({ params }: PageProps) {
  const { slug } = await params;
  const { model, anchorRuns } = await getModelPageData(slug);
  const measuredRuns = model.runs.filter((run) => run.score_status === "measured");
  const omitted = measuredRuns.filter((run) => run.vram_footprint_gb === null).length;

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          <div className="flex flex-wrap gap-2">
            <KindBadge kind={model.kind} runCount={measuredRuns.length} />
          </div>
          <h1 className="mt-3 text-4xl font-semibold text-bench-text">{model.model_label}</h1>
          <p className="mt-2 max-w-3xl text-bench-muted">
            Pick the quant that fits your card now; quality fields stay empty until a benchmark run attaches.
          </p>
        </div>
        <p className="font-mono text-sm text-bench-muted">{omitted} measured run(s) omitted from scatter x.</p>
      </header>
      <QuantDecisionMatrix model={model} />
      <ModelScatter model={model} anchorRuns={anchorRuns} />
      <ModelAxisProfile model={model} />
      <section className="rounded-lg border border-bench-line bg-bench-panel">
        <div className="border-b border-bench-line px-4 py-3">
          <h2 className="text-lg font-semibold text-bench-text">Quant ladder</h2>
        </div>
        <div className="overflow-x-auto">
          <table data-testid="model-runs-table" className="min-w-[1180px] border-collapse text-sm">
            <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
              <tr>
                <th className="px-3 py-3">Run</th>
                <th className="px-3 py-3">Quant</th>
                <th className="px-3 py-3">Footprint</th>
                <th className="px-3 py-3">Composite</th>
                {AXES.map((axis) => (
                  <th key={axis} className="px-3 py-3">
                    {axisLabel(axis)}
                  </th>
                ))}
                <th className="px-3 py-3">Tier</th>
                <th className="px-3 py-3">Lane</th>
                <th className="px-3 py-3">Tokens</th>
                <th className="px-3 py-3">tok/s</th>
                <th className="px-3 py-3">Cost</th>
                <th className="px-3 py-3">Hardware</th>
              </tr>
            </thead>
            <tbody>
              {model.runs.map((run) => (
                <tr key={run.run_id} className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
                  <td className="px-3 py-3">
                    {run.run_id === null ? (
                      <span className="font-mono text-xs text-bench-warn">no run yet</span>
                    ) : (
                      <Link href={`/run/${run.run_id}`} className="font-mono text-bench-accent hover:underline">
                        {run.run_id}
                      </Link>
                    )}
                  </td>
                  <td className="px-3 py-3 text-bench-text">{run.quant_label ?? "n/a"}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">
                    <div>{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</div>
                    {run.file_gb !== null && run.file_gb !== undefined ? (
                      <div className="text-xs text-bench-muted">file {formatGb(run.file_gb)}</div>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 font-mono text-bench-text">
                    {run.composite === null ? (
                      <span className="text-bench-muted">no data yet</span>
                    ) : (
                      <>
                        {formatScore(run.composite.point)} <span className="text-bench-muted">{formatCi(run.composite)}</span>
                      </>
                    )}
                  </td>
                  {AXES.map((axis) => (
                    <td key={axis} className="px-3 py-3 font-mono text-bench-text">
                      {run.axes[axis] === undefined ? <span className="text-bench-muted">no data</span> : formatScore(run.axes[axis].point)}
                    </td>
                  ))}
                  <td className="px-3 py-3">
                    {run.tier === null ? <span className="font-mono text-xs text-bench-muted">not measured</span> : <TierBadge tier={run.tier} />}
                  </td>
                  <td className="px-3 py-3">
                    <LaneBadge lane={run.lane} />
                  </td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatInteger(run.tokens_to_answer_median)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCost(run.est_cost_usd)}</td>
                  <td className="px-3 py-3 text-bench-muted">{formatHardware(run.hardware)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

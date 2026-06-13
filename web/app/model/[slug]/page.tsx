import Link from "next/link";
import { KindBadge, LaneBadge, TierBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ModelScatter } from "@/components/model-scatter";
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
  const omitted = model.runs.filter((run) => run.vram_footprint_gb === null).length;

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          <div className="flex flex-wrap gap-2">
            <KindBadge kind={model.kind} runCount={model.runs.length} />
          </div>
          <h1 className="mt-3 text-4xl font-semibold text-bench-text">{model.model_label}</h1>
          <p className="mt-2 max-w-3xl text-bench-muted">
            All runs and quants for this model, framed against frontier anchor reference lines.
          </p>
        </div>
        <p className="font-mono text-sm text-bench-muted">{omitted} run(s) listed below but omitted from scatter x.</p>
      </header>
      <ModelScatter model={model} anchorRuns={anchorRuns} />
      <section className="rounded-lg border border-bench-line bg-bench-panel">
        <div className="border-b border-bench-line px-4 py-3">
          <h2 className="text-lg font-semibold text-bench-text">Runs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1180px] border-collapse text-sm">
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
                    <Link href={`/run/${run.run_id}`} className="font-mono text-bench-accent hover:underline">
                      {run.run_id}
                    </Link>
                  </td>
                  <td className="px-3 py-3 text-bench-text">{run.quant_label ?? "n/a"}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">
                    {formatScore(run.composite.point)} <span className="text-bench-muted">{formatCi(run.composite)}</span>
                  </td>
                  {AXES.map((axis) => (
                    <td key={axis} className="px-3 py-3 font-mono text-bench-text">
                      {formatScore(run.axes[axis].point)}
                    </td>
                  ))}
                  <td className="px-3 py-3">
                    <TierBadge tier={run.tier} />
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

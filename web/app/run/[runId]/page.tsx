import { Breadcrumbs } from "@/components/breadcrumbs";
import { DetailGrid, DetailItem } from "@/components/detail-grid";
import { RunAxisBreakdown } from "@/components/run-axis-breakdown";
import { presentAxes } from "@/lib/axis-config";
import { getRunData, getRunStaticParams } from "@/lib/data";
import {
  fallbackText,
  formatCi,
  formatCompactNumber,
  formatCost,
  formatHardware,
  formatInteger,
  formatPrimitiveRecord,
  formatRuntime,
  formatScore,
  formatSeconds,
} from "@/lib/format";
import type { RunDetail } from "@/lib/schemas";

export const dynamicParams = false;
const NO_RUNS_STATIC_EXPORT_SENTINEL = "__no-run-receipts-yet";

type PageProps = {
  readonly params: Promise<{
    readonly runId: string;
  }>;
};

export async function generateStaticParams(): Promise<{ runId: string }[]> {
  const params = [...(await getRunStaticParams())];
  return params.length > 0 ? params : [{ runId: NO_RUNS_STATIC_EXPORT_SENTINEL }];
}

export default async function RunPage({ params }: PageProps) {
  const { runId } = await params;
  if (runId === NO_RUNS_STATIC_EXPORT_SENTINEL) {
    return (
      <main className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-5 py-7 lg:px-8">
        <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Run receipts" }]} />
        <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <p className="font-mono text-xs uppercase text-bench-accent">scoreless catalog</p>
          <h1 className="mt-2 text-3xl font-semibold text-bench-text">No run receipts yet</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-bench-muted">
            Catalog model pages are available now. Run receipts appear here only after a benchmark run is published.
          </p>
        </section>
      </main>
    );
  }
  const run = await getRunData(runId);
  const noAnswerCount = Object.values(run.axes).reduce((sum, axis) => sum + axis.n_no_answer, 0);
  const hasQualityNote = run.totals.n_errors > 0 || noAnswerCount > 0;

  return (
    <main className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs
        items={[
          { label: "Leaderboard", href: "/" },
          { label: run.model_label, href: `/model/${runId.split("__")[0]}` },
          { label: "Run" },
        ]}
      />
      <header className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <p className="font-mono text-xs uppercase text-bench-accent">
          {run.suite_version} · {run.index_version}
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-bench-text">{run.model_label}</h1>
        <p className="mt-1 break-all font-mono text-sm text-bench-muted">{run.run_id}</p>
        <div className="mt-5 flex flex-wrap items-end gap-4">
          <div>
            <div className="font-mono text-6xl font-semibold text-bench-text">{formatScore(run.composite.point)}</div>
            <div className="mt-1 font-mono text-lg text-bench-muted">{formatCi(run.composite)} 95% CI</div>
          </div>
          <div className="pb-2 text-sm text-bench-muted">composite, equal-weighted chance-corrected axes</div>
        </div>
        {hasQualityNote ? (
          <div className="mt-5 rounded-md border border-amber-300/35 bg-amber-300/[0.08] p-3 text-sm text-amber-100">
            Data quality note: this run has {run.totals.n_errors} error(s) and {noAnswerCount} no-answer item(s).
          </div>
        ) : null}
      </header>
      <RunAxisBreakdown run={run} />
      <ManifestCard run={run} noAnswerCount={noAnswerCount} />
      <footer className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">Provenance</h2>
        <p className="mt-2 font-mono text-sm text-bench-muted">suite_version: {run.suite_version}</p>
        <p className="mt-1 font-mono text-sm text-bench-muted">index_version: {run.index_version}</p>
        <div className="mt-4 grid gap-2">
          {Object.entries(run.item_set_hashes).map(([name, hash]) => (
            <div key={name} className="grid gap-1 rounded-md border border-bench-line bg-white/[0.025] p-3 md:grid-cols-[220px_1fr]">
              <span className="font-mono text-xs text-bench-muted">{name}</span>
              <span className="break-all font-mono text-xs text-bench-text">{hash}</span>
            </div>
          ))}
        </div>
      </footer>
    </main>
  );
}

function ManifestCard({
  run,
  noAnswerCount,
}: {
  readonly run: RunDetail;
  readonly noAnswerCount: number;
}) {
  const manifest = run.manifest_summary;
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">Manifest</h2>
      <div className="mt-4">
        <DetailGrid>
          <DetailItem label="model" value={manifest.model.family ?? run.model_label} />
          <DetailItem label="quant" value={manifest.quant ?? "n/a"} />
          <DetailItem label="runtime" value={formatRuntime(manifest.runtime, run.kind)} />
          <DetailItem label="hardware" value={formatHardware(manifest.hardware)} />
          <DetailItem label="os" value={manifest.hardware.os ?? "n/a"} />
          <DetailItem label="lane" value={manifest.lane ?? "n/a"} />
          <DetailItem label="thinking_mode" value={manifest.thinking_mode ?? "n/a"} />
          <DetailItem label="caps" value={formatPrimitiveRecord(manifest.caps)} />
          <DetailItem label="sampling" value={formatSampling(run)} />
          <DetailItem
            label="tokens"
            value={`${formatInteger(run.totals.prompt_tokens)} prompt / ${formatInteger(
              run.totals.completion_tokens,
            )} completion / ${formatInteger(run.totals.total_tokens)} total`}
          />
          <DetailItem
            label="tokens-to-answer"
            value={`${formatInteger(run.tokens_to_answer_median)} median / ${formatInteger(
              run.tokens_to_answer_p95,
            )} p95`}
          />
          <DetailItem label="tok/s" value={formatCompactNumber(run.totals.completion_tokens_per_second)} />
          <DetailItem label="wall-time" value={formatSeconds(run.totals.wall_time_seconds)} />
          <DetailItem label="est cost" value={formatCost(run.est_cost_usd)} />
          <DetailItem label="n_items" value={formatInteger(run.totals.n_items)} />
          <DetailItem label="n_errors" value={formatInteger(run.totals.n_errors)} />
          <DetailItem label="n_no_answer" value={formatInteger(noAnswerCount)} />
        </DetailGrid>
      </div>
    </section>
  );
}

function formatSampling(run: RunDetail): string {
  const sampling = run.manifest_summary.sampling;
  const base = [
    `temp ${fallbackText(sampling.temperature)}`,
    `top_p ${fallbackText(sampling.top_p)}`,
    `top_k ${fallbackText(sampling.top_k)}`,
    `min_p ${fallbackText(sampling.min_p)}`,
    `seed ${fallbackText(sampling.seed)}`,
    `effort ${fallbackText(sampling.reasoning_effort)}`,
  ];
  const byBench = presentAxes(sampling.by_bench).map(
    ([axis, bench]) => `${axis}: max ${fallbackText(bench.max_tokens)}`,
  );
  return [...base, ...byBench].join(" · ");
}

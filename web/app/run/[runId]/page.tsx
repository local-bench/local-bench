import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { EngineProvenance } from "@/components/engine-provenance";
import { DetailGrid, DetailItem } from "@/components/detail-grid";
import {
  ModularAxisProfile,
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { RunAxisBreakdown } from "@/components/run-axis-breakdown";
import { IfbenchDecomposition } from "@/components/ifbench-decomposition";
import { LAUNCH_FREEZE } from "@/components/launch-freeze";
import { presentAxes } from "@/lib/axis-config";
import { getRunData, getRunStaticParams } from "@/lib/data";
import {
  fallbackText,
  formatCi,
  formatCompactNumber,
  formatCost,
  formatDuration,
  formatHardware,
  formatInteger,
  formatPrimitiveRecord,
  formatRuntime,
  formatScore,
} from "@/lib/format";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { pageMetadata } from "@/lib/page-metadata";
import { modelHref } from "@/lib/routes";
import type { RunDetail } from "@/lib/schemas";
import {
  SEASON_2_INDEX_PROFILE,
  SEASON_2_INDEX_QUALIFIER,
  displayIndexVersion,
  hasCompleteSeason2Coverage,
  headlineScoreForDisplay,
  legacyBridgeScore,
} from "@/lib/scoring-seasons";

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

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { runId } = await params;
  if (runId === NO_RUNS_STATIC_EXPORT_SENTINEL) {
    return pageMetadata(
      "Run receipts",
      "Published local-bench run receipts will include model, quant, benchmark score, runtime, and hardware evidence.",
    );
  }
  const run = await getRunData(runId);
  const quant = run.manifest_summary.quant ?? "quant unavailable";
  const title = `${run.model_label} ${quant} run receipt — ${LAUNCH_FREEZE.asOfDate}`;
  return pageMetadata(
    title,
    `${run.model_label} ${quant} local benchmark receipt in the board snapshot dated ${LAUNCH_FREEZE.asOfDate}, with scores, runtime, and hardware evidence.`,
  );
}

export default async function RunPage({ params }: PageProps) {
  const { runId } = await params;
  if (runId === NO_RUNS_STATIC_EXPORT_SENTINEL) {
    return (
      <main className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-5 py-7 lg:px-8">
        <Breadcrumbs items={[{ label: "Model families", href: "/families/" }, { label: "Run receipts" }]} />
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
  const dataWarnings = run.data_warnings ?? [];
  const isLegacyReceipt = run.score_status === "measured" && run.lane !== HEADLINE_LANE;
  const season2 = hasCompleteSeason2Coverage(run);
  const effectiveIndexVersion = displayIndexVersion(run);
  const visibleScore = isLegacyReceipt ? (run.diagnostic_composite ?? run.composite) : headlineScoreForDisplay(run);
  const bridgeScore = legacyBridgeScore(run);
  const scoreText = visibleScore === null ? "n/a" : formatScore(visibleScore.point);
  const scoreCiText = visibleScore === null ? "CI unavailable" : `${formatCi(visibleScore)} 95% CI`;
  const scoreTitle = run.ranked ? LOCAL_INTELLIGENCE_INDEX_NAME : "Diagnostic score profile";
  const modelSlug = runId.split("__")[0];

  return (
    <main className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs
        items={[
          { label: "Model families", href: "/families/" },
          { label: run.model_label, href: modelHref(modelSlug) },
          { label: "Run" },
        ]}
      />
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-bench-muted">
          This receipt lets anyone verify this run against the frozen suite — see{" "}
          <Link className="font-semibold text-bench-accent hover:underline" href="/methodology/">Methodology</Link>.
        </p>
        <Link className="font-semibold text-bench-accent hover:underline" href={modelHref(modelSlug)}>
          ← back to {run.model_label}
        </Link>
      </div>
      <header className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <p className="font-mono text-xs uppercase text-bench-accent">
          {isLegacyReceipt ? `${run.suite_version} | retired lane ${run.lane ?? "previous index"}` : `${run.suite_version} | ${effectiveIndexVersion}`}
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-bench-text">{run.model_label}</h1>
        <p className="mt-1 break-all font-mono text-sm text-bench-muted">{run.run_id}</p>
        {isLegacyReceipt ? (
          <div className="mt-5 rounded-md border border-bench-warn/35 bg-bench-warn/[0.08] p-3 text-sm leading-6 text-bench-warn-soft">
            <div className="font-semibold text-bench-text">Previous-index diagnostics</div>
            <p className="mt-1">
              This run was measured under a retired lane on an earlier version of the Index. It is not comparable to the
              current {LOCAL_INTELLIGENCE_INDEX_NAME} and is excluded from ranks, charts, and comparisons.
            </p>
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap items-end gap-4">
          {isLegacyReceipt ? (
            <>
              <div className="pb-2 text-sm text-bench-muted">
                <div className="font-mono text-xs uppercase text-bench-muted">Measured axes (retired lane)</div>
                <ModularAxisProfile axes={run.axes} className="mt-1 block font-mono text-lg text-bench-text" />
                <div className="mt-1">Axis readings and hardware costs remain diagnostic until this variant is re-run on the current lane.</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-bench-text">Diagnostic score (retired lane)</div>
                <div className="font-mono text-xs text-bench-accent">{run.lane ?? "previous index"}</div>
                <div className="font-mono text-3xl font-semibold text-bench-text">{scoreText}</div>
                <div className="mt-1 font-mono text-sm text-bench-muted">{scoreCiText}</div>
              </div>
            </>
          ) : (
            <>
              <div>
                <div className="text-sm font-semibold text-bench-text">{scoreTitle}</div>
                <div className="font-mono text-xs text-bench-accent">{season2 ? SEASON_2_INDEX_QUALIFIER : LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</div>
                <div className="font-mono text-6xl font-semibold text-bench-text">{scoreText}</div>
                <div className="mt-1 font-mono text-lg text-bench-muted">{scoreCiText}</div>
                {bridgeScore === null ? null : (
                  <div className="mt-1 font-mono text-xs text-bench-muted">index-v3.0 bridge {formatScore(bridgeScore.point)}</div>
                )}
              </div>
              <div className="pb-2 text-sm text-bench-muted">
                <div className="font-mono text-xs uppercase text-bench-muted">{season2 ? SEASON_2_INDEX_PROFILE : LOCAL_INTELLIGENCE_INDEX_PROFILE}</div>
                <ModularAxisProfile axes={run.axes} className="mt-1 block font-mono text-sm text-bench-text" />
                <div className="mt-1">{season2
                  ? "Weighted headline profile: Agentic 25%, Knowledge 22.5%, Instruction 22.5%, Coding 22.5%, Math 7.5%."
                  : "Weighted headline profile: Agentic 40%, Knowledge 15%, Instruction 15%, Tool 10%, Coding 15%, Math 5%."}</div>
              </div>
            </>
          )}
          <div className="pb-2 text-sm text-bench-muted">
            <div className="font-mono text-xs uppercase text-bench-muted">Total run time</div>
            <div className="mt-1 font-mono text-lg text-bench-text">{formatDuration(run.totals.wall_time_seconds)}</div>
          </div>
        </div>
        {hasQualityNote ? (
          <div className="mt-5 rounded-md border border-bench-warn/35 bg-bench-warn/[0.08] p-3 text-sm text-bench-warn-soft">
            Data quality note: this run has {run.totals.n_errors} error(s) and {noAnswerCount} no-answer item(s).
          </div>
        ) : null}
        {!run.ranked && !isLegacyReceipt ? (
          <div className="mt-5 rounded-md border border-bench-warn/35 bg-bench-warn/[0.08] p-3 text-sm leading-6 text-bench-warn-soft">
            {dataWarnings.includes("agentic-infra-timeout-rate")
              ? "Unranked diagnostic: the agentic phase of this run shows an elevated or unverifiable infrastructure timeout rate, so its measured axes stay visible but it does not receive a ranked Local Intelligence Index position until re-run on hardware that clears it."
              : "Unranked diagnostic: this receipt is missing one or more headline axes for the current index. It is useful for comparing measured axes, but it does not receive a ranked Local Intelligence Index position."}
          </div>
        ) : null}
        {dataWarnings.length > 0 ? (
          <div className="mt-5 rounded-md border border-bench-line bg-white/[0.025] p-3 text-sm leading-6 text-bench-muted">
            <div className="font-semibold text-bench-text">Data warnings</div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {dataWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </header>
      <RunAxisBreakdown run={run} />
      <IfbenchDecomposition axis={run.axes.instruction} />
      {run.perf === undefined ? (
        <ManifestCard run={run} noAnswerCount={noAnswerCount} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_430px]">
          <ManifestCard run={run} noAnswerCount={noAnswerCount} />
          <ServingPerformanceCard run={run} />
        </div>
      )}
      <footer className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">Provenance</h2>
        <p className="mt-2 font-mono text-sm text-bench-muted">suite_version: {run.suite_version}</p>
        <p className="mt-1 font-mono text-sm text-bench-muted">index_version: {effectiveIndexVersion}</p>
        {run.scorecard === undefined ? null : (
          <div className="mt-3 rounded-md border border-bench-line bg-white/[0.025] p-3 text-sm leading-6 text-bench-muted">
            <div className="font-mono text-xs uppercase text-bench-muted">source scorecard</div>
            <p className="mt-1 font-mono text-bench-text">version: {run.scorecard.version ?? "n/a"}</p>
            <p className="mt-1 break-all font-mono text-xs">id: {run.scorecard.id ?? "n/a"}</p>
            {run.scorecard.drift || run.scorecard.registry_drift ? (
              <p className="mt-2 text-bench-warn-soft">
                Provenance drift: this receipt preserves its original scorecard metadata; the site projection is
                rendered under {effectiveIndexVersion}.
              </p>
            ) : null}
          </div>
        )}
        <EngineProvenance provenance={run.serving_provenance} />
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
          <DetailItem label="total run time" value={formatDuration(run.totals.wall_time_seconds)} />
          <DetailItem label="est cost" value={formatCost(run.est_cost_usd)} />
          <DetailItem label="n_items" value={formatInteger(run.totals.n_items)} />
          <DetailItem label="n_errors" value={formatInteger(run.totals.n_errors)} />
          <DetailItem label="n_no_answer" value={formatInteger(noAnswerCount)} />
        </DetailGrid>
      </div>
    </section>
  );
}

export function ServingPerformanceCard({ run }: { readonly run: RunDetail }) {
  const perf = run.perf;
  if (perf === undefined) {
    return null;
  }
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">Serving performance</h2>
      <p className="mt-1 text-sm leading-6 text-bench-muted">{formatHardware(run.manifest_summary.hardware)}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Metric label="prefill" value={formatTokPerSecond(perf.prefill_tps)} />
        <Metric label="decode" value={formatTokPerSecond(perf.decode_tps)} />
        <Metric
          label="TTFT proxy"
          value={formatMilliseconds(perf.ttft_proxy_ms_median)}
          note="prompt processing before first token — non-streaming harness, lower bound"
        />
        <Metric label="coverage" value={formatCoverage(perf.timings_coverage)} />
        <Metric label="prompt median / p95" value={`${formatMilliseconds(perf.prompt_ms_median)} / ${formatMilliseconds(perf.prompt_ms_p95)}`} />
        <Metric
          label="predicted median / p95"
          value={`${formatMilliseconds(perf.predicted_ms_median)} / ${formatMilliseconds(perf.predicted_ms_p95)}`}
        />
      </div>
      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="text-left font-mono text-[11px] uppercase tracking-wider text-bench-text/80">
            <tr>
              <th className="border-b border-bench-line px-2 py-2 font-semibold">bench</th>
              <th className="border-b border-bench-line px-2 py-2 font-semibold">prefill</th>
              <th className="border-b border-bench-line px-2 py-2 font-semibold">decode</th>
              <th className="border-b border-bench-line px-2 py-2 font-semibold">prompt median</th>
              <th className="border-b border-bench-line px-2 py-2 font-semibold">n</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(perf.per_bench).map(([bench, benchPerf]) => (
              <tr key={bench} className="border-b border-bench-line/70">
                <td className="px-2 py-2 font-mono text-xs text-bench-text">{bench}</td>
                <td className="px-2 py-2 font-mono text-xs text-bench-muted">{formatTokPerSecond(benchPerf.prefill_tps)}</td>
                <td className="px-2 py-2 font-mono text-xs text-bench-muted">{formatTokPerSecond(benchPerf.decode_tps)}</td>
                <td className="px-2 py-2 font-mono text-xs text-bench-muted">{formatMilliseconds(benchPerf.prompt_ms_median)}</td>
                <td className="px-2 py-2 font-mono text-xs text-bench-muted">{formatInteger(benchPerf.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 font-mono text-[11px] text-bench-muted">
        {perf.timings_source === null ? "Server timings: not measured." : `Source: ${perf.timings_source} server timings.`}
      </p>
    </section>
  );
}

function Metric({
  label,
  value,
  note,
}: {
  readonly label: string;
  readonly value: string;
  readonly note?: string;
}) {
  return (
    <div className="rounded border border-bench-line bg-white/[0.025] p-3">
      <div className="font-mono text-[10px] uppercase text-bench-muted">{label}</div>
      <div className="mt-1 font-mono text-base text-bench-text">{value}</div>
      {note === undefined ? null : <div className="mt-1 text-xs leading-5 text-bench-muted">{note}</div>}
    </div>
  );
}

function formatTokPerSecond(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${formatCompactNumber(value)} tok/s`;
}

function formatMilliseconds(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${formatCompactNumber(value)} ms`;
}

function formatCoverage(value: number): string {
  return `${formatScore(Math.max(0, Math.min(1, value)) * 100)}%`;
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
  return [...base, ...byBench].join(" | ");
}

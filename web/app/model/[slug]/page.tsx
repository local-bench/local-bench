import { KindBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ConformancePill } from "@/components/conformance-pill";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import { AxisMiniBar } from "@/components/score-bar";
import { getModelPageData, getModelStaticParams } from "@/lib/data";

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
  const rankedRuns = measuredRuns.filter((run) => run.ranked);
  const partialRuns = measuredRuns.filter((run) => !run.ranked);
  const bestMeasuredRun = measuredRuns.reduce<(typeof measuredRuns)[number] | undefined>(
    (best, run) => (best === undefined || (run.composite?.point ?? -Infinity) > (best.composite?.point ?? -Infinity) ? run : best),
    undefined,
  );
  const toolCallingAxis = bestMeasuredRun?.axes.tool_calling;
  const formatGate = model.runs.find((run) => run.conformance_gates?.tc_json_v1 !== undefined)?.conformance_gates
    ?.tc_json_v1;

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
            This model&apos;s quants and distills, with ranks assigned only to complete five-axis Local Intelligence Index
            rows. Partial profiles remain useful diagnostics; the VRAM and speed columns show what each rung costs.
          </p>
          {partialRuns.length > 0 && rankedRuns.length === 0 ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-warn-soft">
              {partialRuns.length} measured profile{partialRuns.length === 1 ? "" : "s"} are unranked because at least
              one headline axis is missing.
            </p>
          ) : null}
        </div>
      </header>
      <section className="rounded-lg border border-bench-line bg-bench-panel/82 px-4 py-3">
        <h2 className="text-sm font-semibold uppercase text-bench-muted">Tool calling</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-bench-muted">
          <span className="font-mono text-bench-text">tc_json_v1</span>
          <span>plaintext tool-call benchmark</span>
          <AxisMiniBar score={toolCallingAxis} />
          <span className="font-mono">n={toolCallingAxis?.n ?? "n/a"}</span>
          {formatGate === undefined ? null : (
            <>
              <span>format gate</span>
              <ConformancePill gate={formatGate} showReason compact />
            </>
          )}
          <span>Weighted axis; 10% Local Intelligence Index weight.</span>
        </div>
        <p className="mt-2 text-xs leading-5 text-bench-muted">
          Tool calling tests single-turn tool selection and argument construction. Agentic tests multi-turn Python code-as-action task completion. They may correlate; they are not independent votes.
        </p>
      </section>
      <ModelVariantBoard model={model} />
      <ModelScatter model={model} anchorRuns={anchorRuns} />
    </main>
  );
}

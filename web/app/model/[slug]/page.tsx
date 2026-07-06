import Link from "next/link";
import { RunByBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import { ProvenanceLabels } from "@/components/leaderboard-provenance";
import { VsBaseStrip } from "@/components/vs-base-strip";
import { getModelPageData, getModelStaticParams } from "@/lib/data";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";

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
  const { model, anchorRuns, lineage, vsBaseComparisons } = await getModelPageData(slug);
  // Current-index (headline lane) runs drive every headline element; legacy-lane runs are
  // diagnostics from an earlier index version and only inform the fallback copy below.
  const headlineMeasured = model.runs.filter(
    (run) => run.score_status === "measured" && run.lane === HEADLINE_LANE,
  );
  const legacyMeasured = model.runs.filter(
    (run) => run.score_status === "measured" && run.lane !== HEADLINE_LANE,
  );
  const measuredRuns = [...headlineMeasured, ...legacyMeasured];
  const rankedRuns = headlineMeasured.filter((run) => run.ranked);
  const partialRuns = headlineMeasured.filter((run) => !run.ranked);
  // Headline provenance comes from the ranked (representative) run when one exists —
  // ladder/partial runs sort first in the payload and must not set the headline chip.
  const hasProvenance = (run: (typeof measuredRuns)[number]): boolean =>
    run.origin !== undefined || run.trust_label !== undefined || run.agentic_provenance !== undefined;
  const provenanceRun = rankedRuns.find(hasProvenance) ?? measuredRuns.find(hasProvenance);
  const submitter = measuredRuns.find(
    (run) => run.submitter_display_name !== null && run.submitter_display_name !== undefined,
  )?.submitter_display_name;
  const formatGate = measuredRuns.find((run) => run.conformance_gates?.tc_json_v1 !== undefined)?.conformance_gates
    ?.tc_json_v1;

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          {measuredRuns.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              <RunByBadge submitter={submitter} />
            </div>
          ) : null}
          <h1 className="mt-3 text-4xl font-semibold text-bench-text">{model.model_label}</h1>
          {lineage !== null ? (
            <div className="mt-3">
              {lineage.baseSlug !== null ? (
                <Link
                  href={`/model/${lineage.baseSlug}`}
                  className="inline-flex rounded border border-bench-line bg-bench-panel-2 px-2.5 py-1 font-mono text-[11px] uppercase text-bench-accent hover:border-bench-accent"
                >
                  Fine-tune of {lineage.baseDisplayName}
                </Link>
              ) : (
                <span className="inline-flex rounded border border-bench-line bg-bench-panel-2 px-2.5 py-1 font-mono text-[11px] uppercase text-bench-muted">
                  Fine-tune of {lineage.baseDisplayName}
                </span>
              )}
            </div>
          ) : null}
          {provenanceRun === undefined ? null : <ProvenanceLabels model={provenanceRun} />}
          <p className="mt-2 max-w-3xl text-bench-muted">
            This model&apos;s quants and distills, with ranks assigned only to complete current-index Local Intelligence
            rows. Partial profiles remain useful diagnostics; the VRAM and speed columns show what each rung costs.
          </p>
          {partialRuns.length > 0 && rankedRuns.length === 0 ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-warn-soft">
              {partialRuns.length} measured profile{partialRuns.length === 1 ? " is" : "s are"} unranked because at
              least one headline axis is missing.
            </p>
          ) : null}
          {legacyMeasured.length > 0 && headlineMeasured.length === 0 ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-warn-soft">
              All {legacyMeasured.length} measured profile{legacyMeasured.length === 1 ? "" : "s"} for this model come
              from a previous index lane. They appear below as diagnostics; the model rejoins the ranked board once a
              current-index run lands.
            </p>
          ) : null}
        </div>
      </header>
      <VsBaseStrip label={lineage === null ? "vs fine-tunes" : "vs base"} comparisons={vsBaseComparisons} />
      <ModelVariantBoard model={model} formatGate={formatGate} />
      <ModelScatter model={model} anchorRuns={anchorRuns} />
    </main>
  );
}

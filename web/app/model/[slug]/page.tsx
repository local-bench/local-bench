import Link from "next/link";
import { RunByBadge } from "@/components/badges";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { CatalogOnlyNotice } from "@/components/catalog-only-notice";
import { CommunityFamilyResultsLive } from "@/components/community-family-results";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import { ProvenanceLabels } from "@/components/leaderboard-provenance";
import { RuntimeBadge } from "@/components/runtime-badge";
import { VsBaseStrip } from "@/components/vs-base-strip";
import { getModelPageData, getModelStaticParams } from "@/lib/data";
import { communityRowsForModel, getCommunityBoardRows } from "@/lib/community-data";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { isTrustedPopulation, isTrustedRankedPopulation, selectTrustedHeaderSource } from "@/lib/trusted-population";

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
  const { model, anchorRuns, catalogOnly, familyModels, lineage, queued, vsBaseComparisons } = await getModelPageData(slug);
  const communityRows = await getCommunityBoardRows();
  const communityFamilyRows = communityRows === null
    ? []
    : communityRowsForModel(communityRows, { catalogId: model.catalog_id, family: model.family });
  // Only current-index (headline lane) runs inform this page. Retired-lane runs stay
  // reachable by direct /run URL but are not surfaced here (owner call, 2026-07-09 —
  // migration bookkeeping reads as noise to visitors who never saw the old index).
  const headlineMeasured = model.runs.filter(
    (run) => run.score_status === "measured" && run.lane === HEADLINE_LANE,
  );
  const trustedHeadlineMeasured = headlineMeasured.filter(isTrustedPopulation);
  const rankedRuns = trustedHeadlineMeasured.filter(isTrustedRankedPopulation);
  const partialRuns = trustedHeadlineMeasured.filter((run) => !run.ranked);
  // Headline provenance comes from the ranked (representative) run when one exists —
  // ladder/partial runs sort first in the payload and must not set the headline chip.
  const hasProvenance = (run: (typeof headlineMeasured)[number]): boolean =>
    run.origin !== undefined || run.trust_label !== undefined || run.agentic_provenance !== undefined;
  const provenanceRun = selectTrustedHeaderSource(rankedRuns.filter(hasProvenance));
  const submitter = trustedHeadlineMeasured.find(
    (run) => run.submitter_display_name !== null && run.submitter_display_name !== undefined,
  )?.submitter_display_name;

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          {trustedHeadlineMeasured.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              <RunByBadge submitter={submitter} />
            </div>
          ) : null}
          <h1 className="mt-3 flex items-center gap-3 text-4xl font-semibold text-bench-text">
            <FamilyLogoMark modelLabel={model.model_label} size={32} className="rounded" />
            {model.model_label}
          </h1>
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
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[...new Map(rankedRuns.map((run) => [run.runtime.name, run.runtime])).values()].map((runtime) => (
              <RuntimeBadge key={runtime.name ?? "unknown"} runtime={runtime} />
            ))}
          </div>
          <p className="mt-2 max-w-3xl text-bench-muted">
            Every measured variant of this model: how much quality each quant keeps, and the VRAM and speed it costs
            to run.
          </p>
          {partialRuns.length > 0 && rankedRuns.length === 0 ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-warn-soft">
              {partialRuns.length} measured profile{partialRuns.length === 1 ? " is" : "s are"} unranked — each run
              receipt states the reason (a missing headline axis or a data-quality gate).
            </p>
          ) : null}
        </div>
      </header>
      {catalogOnly ? <CatalogOnlyNotice queued={queued} /> : null}
      <ModelScatter model={model} anchorRuns={anchorRuns} familyModels={familyModels} />
      <ModelVariantBoard model={model} familyModels={familyModels} />
      <CommunityFamilyResultsLive
        rows={communityFamilyRows}
        target={{ catalogId: model.catalog_id, family: model.family }}
      />
      <VsBaseStrip label={lineage === null ? "vs fine-tunes" : "vs base"} comparisons={vsBaseComparisons} />
    </main>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { CatalogOnlyNotice } from "@/components/catalog-only-notice";
import { CommunityFamilyResultsLive } from "@/components/community-family-results";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import { ProjectRunBadge } from "@/components/leaderboard-provenance";
import { RuntimeBadge } from "@/components/runtime-badge";
import { VsBaseStrip } from "@/components/vs-base-strip";
import { getModelPageData, getModelStaticParams } from "@/lib/data";
import { communityRowsForModel, getCommunityBoardRows } from "@/lib/community-data";
import { communityRowCatalogIds, communityRowsWithFamilyPaths } from "@/lib/community-family";
import { familyResolutionContext } from "@/lib/family-resolution-data";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { estimateRunVram } from "@/lib/model-run-metrics";
import { pageMetadata } from "@/lib/page-metadata";
import { modelHref } from "@/lib/routes";
import { formatGb, formatScore } from "@/lib/format";
import { hasCompleteSeason2Coverage, headlineScoreForDisplay, INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

export const dynamicParams = false;

type PageProps = {
  readonly params: Promise<{
    readonly slug: string;
  }>;
};

export async function generateStaticParams(): Promise<{ slug: string }[]> {
  return [...(await getModelStaticParams())];
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const { model } = await getModelPageData(slug);
  const title = `${model.model_label} — local benchmark scores, quants, VRAM`;
  const bestRun = model.runs
    .filter((run) => run.score_status === "measured" && run.lane === HEADLINE_LANE && isCompleteRun(run))
    .sort((left, right) =>
      (headlineScoreForDisplay(right)?.point ?? Number.NEGATIVE_INFINITY) -
      (headlineScoreForDisplay(left)?.point ?? Number.NEGATIVE_INFINITY),
    )[0];
  const bestScore = bestRun === undefined ? null : headlineScoreForDisplay(bestRun);
  if (bestRun === undefined || bestScore === null) {
    return pageMetadata(
      title,
      `${model.model_label} is awaiting a complete local-bench run. Browse known quants and benchmark it on local hardware.`,
    );
  }
  const quant = bestRun.quant_label ?? "unlabelled quant";
  const vram = estimateRunVram(bestRun, model.runs)?.effectiveRequiredGb ?? null;
  const vramCopy = vram === null ? "VRAM @8k is not yet available" : `estimated VRAM @8k ${formatGb(vram)}`;
  return pageMetadata(
    title,
    `${model.model_label} best complete run: ${formatScore(bestScore.point)} composite with ${quant}; ${vramCopy}.`,
  );
}

export default async function ModelPage({ params }: PageProps) {
  const { slug } = await params;
  const { model, anchorRuns, catalogOnly, familyModels, lineage, queued, vsBaseComparisons } = await getModelPageData(slug);
  const communityRows = await getCommunityBoardRows();
  const resolutionContext = familyResolutionContext();
  const artifactSha256s = model.artifacts?.map((artifact) => artifact.file_sha256);
  const communityTarget = {
    catalogId: model.catalog_id,
    family: model.family,
    modelLabel: model.model_label,
    slug: model.slug,
    ...(artifactSha256s === undefined ? {} : { artifactSha256s }),
  };
  const communityFamilyRows = communityRows === null
    ? []
    : communityRowsForModel(
        communityRowsWithFamilyPaths(communityRows, resolutionContext),
        communityTarget,
      );
  // Only current-index (headline lane) runs inform this page. Retired-lane runs stay
  // reachable by direct /run URL but are not surfaced here (owner call, 2026-07-09 —
  // migration bookkeeping reads as noise to visitors who never saw the old index).
  const headlineMeasured = model.runs.filter(
    (run) => run.score_status === "measured" && run.lane === HEADLINE_LANE,
  );
  const rankedRuns = headlineMeasured.filter(isCompleteRun);
  const partialRuns = headlineMeasured.filter((run) => !isCompleteRun(run));
  const hasProjectRun = rankedRuns.some((run) => run.origin === "project_anchor");
  const communityCatalogIds = communityRowCatalogIds(communityFamilyRows);
  const visibleComparisons = vsBaseComparisons.filter(
    (comparison) => !communityCatalogIds.has(comparison.derivative.catalogId),
  );

  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 px-5 py-7 lg:px-8">
      <Breadcrumbs items={[{ label: "Model families", href: "/families/" }, { label: model.model_label }]} />
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-bench-line pb-5">
        <div>
          {hasProjectRun ? (
            <div className="flex flex-wrap gap-2">
              <ProjectRunBadge origin="project_anchor" />
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
                  href={modelHref(lineage.baseSlug)}
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
        resolutionContext={resolutionContext}
        target={communityTarget}
      />
      <VsBaseStrip label={lineage === null ? "vs fine-tunes" : "vs base"} comparisons={visibleComparisons} />
    </main>
  );
}

function isCompleteRun(run: Awaited<ReturnType<typeof getModelPageData>>["model"]["runs"][number]): boolean {
  if (run.index_version === INDEX_VERSION_V4) return hasCompleteSeason2Coverage(run);
  return ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => {
    const score = run.axes[axis];
    return score !== undefined && score.n > 0;
  }) && run.composite !== null;
}

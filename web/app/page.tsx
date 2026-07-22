import Link from "next/link";
import { BenchmarkOnramp } from "@/components/benchmark-onramp";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { HeroBanner } from "@/components/hero-banner";
import { HomeLeaderboard } from "@/components/home-leaderboard";
import { ReplicationTimePanel } from "@/components/replication-time-panel";
import { selectBestVariantPoints } from "@/lib/best-variant";
import { getCommunityBoardRows } from "@/lib/community-data";
import { communityRowsWithFamilyPaths } from "@/lib/community-family";
import {
  getAgenticBySlug,
  getHomePageData,
  getOnrampCatalog,
} from "@/lib/data";
import { familyResolutionContext } from "@/lib/family-resolution-data";
import { familyRootLabelBySlug } from "@/lib/family-resolution";
import { isFullIndexRow, scoreForMode } from "@/lib/leaderboard-score";
import { INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

export default async function HomePage() {
  const [{ anchorRuns, catalogModels, communityCatalogModels, index, rigCandidates }, catalog, agenticBySlug, communityRows] = await Promise.all([
    getHomePageData(),
    getOnrampCatalog(),
    getAgenticBySlug(),
    getCommunityBoardRows(),
  ]);
  const resolutionContext = familyResolutionContext(communityCatalogModels);
  const bestVariantPoints = selectBestVariantPoints(rigCandidates, { catalogModels });
  const fineTuneBaseBySlug = familyRootLabelBySlug(index.models, resolutionContext);
  const ranked = index.models.filter(isFullIndexRow);
  const rankedForDisplay = index.index_version === INDEX_VERSION_V4
    ? ranked.map((model) => model.index_version === undefined ? { ...model, index_version: INDEX_VERSION_V4 } : model)
    : ranked;
  const vramBySlug = new Map(communityCatalogModels.map((model) => [model.slug, model.vramRequiredGb8k] as const));
  const quantBySlug = new Map(communityCatalogModels.map((model) => [model.slug, model.quantLabel] as const));
  const communityArtifactDetails = communityCatalogModels.flatMap((model) => model.artifactDetails ?? []);
  const communityRowsForDisplay = communityRows === null
    ? []
    : communityRowsWithFamilyPaths(communityRows, resolutionContext);
  const benchmarkedModels = ranked.flatMap((model) => {
    const score = scoreForMode(model, "full");
    return score === null ? [] : [{ score: score.point, slug: model.slug }];
  });

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <HeroBanner />
      {/* Side-by-side only when the scatter keeps its useful width (xl+); stacked below that. */}
      <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)] xl:items-stretch">
        <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
        {/* The panel and ranked table share the canonical family resolver: each catalog root
            contributes the same winning measured variant, so hidden fine-tunes cannot leak here. */}
        <ReplicationTimePanel points={bestVariantPoints} />
      </div>
      <section className="grid gap-2">
        <p className="text-sm text-bench-muted">
          Showing the best variant per base family —{" "}
          <Link href="/leaderboard/" className="font-semibold text-bench-accent hover:underline">full board →</Link>
        </p>
        <HomeLeaderboard
          models={rankedForDisplay}
          agenticBySlug={agenticBySlug}
          communityArtifactDetails={communityArtifactDetails}
          communityRows={communityRowsForDisplay}
          fineTuneBaseBySlug={fineTuneBaseBySlug}
          indexVersion={index.index_version}
          quantBySlug={quantBySlug}
          resolutionContext={resolutionContext}
          vramBySlug={vramBySlug}
        />
      </section>
      <div id="run-it-yourself" className="scroll-mt-24">
        <BenchmarkOnramp
          benchmarkedModels={benchmarkedModels}
          catalog={catalog.models}
          popularityAsOf={catalog.popularityAsOf}
        />
      </div>
      <Link
        href="/leaderboard/"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View global comparison →
      </Link>
    </main>
  );
}

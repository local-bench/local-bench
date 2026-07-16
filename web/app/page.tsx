import Link from "next/link";
import { BenchmarkOnramp } from "@/components/benchmark-onramp";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { HeroBanner } from "@/components/hero-banner";
import { ReplicationTimePanel } from "@/components/replication-time-panel";
import { getHomePageData, getOnrampCatalog } from "@/lib/data";
import { selectBestModelVariantPoints, selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, catalogModels, rigCandidates } = await getHomePageData();
  const catalog = await getOnrampCatalog();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates, { catalogModels });
  const bestModelVariantPoints = selectBestModelVariantPoints(rigCandidates);

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <HeroBanner />
      {/* Side-by-side only when the scatter keeps its useful width (xl+); stacked below that. */}
      <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)] xl:items-stretch">
        <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
        {/* Per-model points (same population as the ranked table), NOT the scatter's
            family-rooted points — fine-tunes hold their own leaderboard rank, and folding
            them into the base family would shift every rank label below them. */}
        <ReplicationTimePanel points={bestModelVariantPoints} />
      </div>
      <BestVariantTable points={bestModelVariantPoints} />
      <div id="run-it-yourself" className="scroll-mt-24">
        <BenchmarkOnramp catalog={catalog.models} popularityAsOf={catalog.popularityAsOf} />
      </div>
      <Link
        href="/leaderboard"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View full leaderboard →
      </Link>
    </main>
  );
}

import Link from "next/link";
import { BenchmarkOnramp } from "@/components/benchmark-onramp";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { HeroBanner } from "@/components/hero-banner";
import { getHomePageData, getOnrampCatalog } from "@/lib/data";
import { selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, rigCandidates } = await getHomePageData();
  const catalog = await getOnrampCatalog();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates);

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <HeroBanner />
      <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
      <BestVariantTable points={bestVariantPoints} />
      <BenchmarkOnramp catalog={catalog.models} popularityAsOf={catalog.popularityAsOf} />
      <Link
        href="/leaderboard"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View full leaderboard →
      </Link>
    </main>
  );
}

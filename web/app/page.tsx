import Link from "next/link";
import { RigMatchFinder } from "@/components/rig-match-finder";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { getHomePageData } from "@/lib/data";
import { selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, rigAnchors, rigCandidates } = await getHomePageData();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates);

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
      <BestVariantTable points={bestVariantPoints} />
      <RigMatchFinder anchors={rigAnchors} candidates={rigCandidates.filter((candidate) => candidate.lane !== "answer-only")} />
      <Link
        href="/leaderboard"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View full leaderboard →
      </Link>
    </main>
  );
}

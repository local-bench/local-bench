import { CommunityListingLive } from "@/components/community-listing";
import { getCommunityBoardRows, getCommunityGroups } from "@/lib/community-data";

export default async function CommunityPage() {
  const [groups, bakedRows] = await Promise.all([getCommunityGroups(), getCommunityBoardRows()]);
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-5 py-8">
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs uppercase text-bench-accent">Community submissions</p>
        <h1 className="mt-2 text-3xl font-semibold text-bench-text">Community models</h1>
        <p className="mt-2 max-w-3xl text-sm text-bench-muted">
          Published, unranked community benchmark records. Identity and lineage labels describe evidence, not verification.
        </p>
      </header>
      <CommunityListingLive bakedRows={bakedRows ?? []} groups={groups} />
    </main>
  );
}

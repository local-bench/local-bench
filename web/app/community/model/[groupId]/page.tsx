import { CommunityDetailLive } from "@/components/community-detail";
import {
  COMMUNITY_GROUP_PLACEHOLDER_ID,
  communityBoardRows,
  getCommunityGroup,
  getCommunityGroupStaticParams,
} from "@/lib/community-data";

export const dynamicParams = false;

export async function generateStaticParams(): Promise<{ groupId: string }[]> {
  return [...await getCommunityGroupStaticParams()];
}

export default async function CommunityModelPage({ params }: { readonly params: Promise<{ readonly groupId: string }> }) {
  const { groupId } = await params;
  if (groupId === COMMUNITY_GROUP_PLACEHOLDER_ID) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-5 py-8">
        <header className="border-b border-bench-line pb-5">
          <p className="font-mono text-xs uppercase text-bench-accent">Unranked community lane</p>
          <h1 className="mt-2 text-3xl font-semibold text-bench-text">Community model group</h1>
          <p className="mt-2 font-mono text-sm text-bench-muted">No community model groups have been published yet.</p>
        </header>
      </main>
    );
  }
  const group = await getCommunityGroup(groupId);
  const bakedRows = group === null ? [] : communityBoardRows([group]);
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-5 py-8">
      <CommunityDetailLive
        bakedRows={bakedRows}
        group={group}
        groupId={`community-group:${groupId}`}
      />
    </main>
  );
}

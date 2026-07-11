import { getCommunityGroup, getCommunityGroupStaticParams } from "@/lib/data";

export const dynamicParams = false;

export async function generateStaticParams(): Promise<{ groupId: string }[]> {
  return [...await getCommunityGroupStaticParams()];
}

export default async function CommunityModelPage({ params }: { readonly params: Promise<{ readonly groupId: string }> }) {
  const { groupId } = await params;
  const group = await getCommunityGroup(groupId);
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-5 py-8">
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs uppercase text-bench-accent">Unranked community lane</p>
        <h1 className="mt-2 text-3xl font-semibold text-bench-text">Community model group</h1>
        <p className="mt-2 font-mono text-sm text-bench-muted">{group.identity_label}</p>
        <p className="mt-1 font-mono text-xs text-bench-muted">{group.community_model_group_id}</p>
      </header>
      <section className="grid gap-4" data-testid="community-variants">
        {group.variants.map((variant) => (
          <article key={variant.submission_id} className="rounded border border-bench-line bg-bench-panel p-4">
            <h2 className="text-lg font-semibold text-bench-text">{variant.display_name ?? "Community-declared variant"}</h2>
            <p className="mt-1 font-mono text-xs uppercase text-bench-muted">unranked · artifact {variant.artifact_sha256.slice(0, 16)}</p>
            <p className="mt-2 font-mono text-xs text-bench-muted">submission {variant.submission_id}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

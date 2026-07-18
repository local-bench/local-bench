import { huggingFaceRepoUrl, type CommunityGroupData } from "@/lib/community-data";

export function CommunityDetail({ group }: { readonly group: CommunityGroupData | null }) {
  if (group === null) {
    return (
      <section className="rounded border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">Community data unavailable</h2>
        <p className="mt-2 text-sm text-bench-muted">This community record could not be validated.</p>
      </section>
    );
  }
  return (
    <>
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
            <p className="mt-1 font-mono text-xs uppercase text-bench-muted">
              unranked · {variant.quant_label ?? "quant unavailable"} · artifact {variant.artifact_sha256.slice(0, 16)}
            </p>
            <p className="mt-2 font-mono text-xs text-bench-muted">submission {variant.submission_id}</p>
            {variant.lineage_enrichment === undefined ? null : (
              <LineageSection lineage={variant.lineage_enrichment} />
            )}
          </article>
        ))}
      </section>
    </>
  );
}

function LineageSection({
  lineage,
}: {
  readonly lineage: NonNullable<CommunityGroupData["variants"][number]["lineage_enrichment"]>;
}) {
  return (
    <section className="mt-5 border-t border-bench-line pt-4" aria-label="HF model-card-declared lineage (unverified)">
      <h3 className="text-base font-semibold text-bench-text">HF model-card-declared lineage (unverified)</h3>
      <div className="mt-3 rounded border border-bench-line bg-bench-bg/40 p-3">
        <p className="font-mono text-xs uppercase text-bench-accent">Layer 1 — artifact → repository association</p>
        <p className="mt-1 text-sm text-bench-text">This association is maintainer-associated and unproven.</p>
        <p className="mt-1 text-sm text-bench-muted">{lineage.association.note}</p>
        <a
          href={huggingFaceRepoUrl(lineage.repo.id)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Open Hugging Face repository: ${lineage.repo.id}`}
          className="mt-2 inline-block text-sm font-medium text-bench-accent hover:text-bench-text"
        >
          {lineage.repo.id} · {lineage.repo.revision.slice(0, 7)}
        </a>
      </div>
      <p className="mt-4 font-mono text-xs uppercase text-bench-accent">Repository owner model-card claims</p>
      <p className="mt-1 text-sm text-bench-muted">
        Each arrow below is the child repository owner’s card declaration, not an independently verified ancestry claim.
      </p>
      <ol className="mt-3 grid gap-2">
        {lineage.card_declared_edges.map((edge, index) => (
          <li key={`${edge.child}@${edge.child_revision}`} className="rounded border border-bench-line p-3 text-sm text-bench-text">
            <span className="font-mono text-xs uppercase text-bench-muted">
              Layer {index + 2} — repository owner’s model-card claim
            </span>
            <p className="mt-1">
              {edge.child} @ {edge.child_revision.slice(0, 7)} → {edge.base} @ {edge.base_revision?.slice(0, 7) ?? "unresolved"}
            </p>
          </li>
        ))}
      </ol>
      <p className="mt-3 font-mono text-xs text-bench-muted">
        Maintainer resolution: {lineage.resolution.status} · {lineage.resolution.resolved_at}
      </p>
    </section>
  );
}

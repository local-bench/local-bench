"use client";

import Link from "next/link";
import { CommunityFreshness, useLiveCommunityRows } from "@/components/community-live-state";
import { AttributionChip, TrustTierChip } from "@/components/leaderboard-provenance";
import type { CommunityBoardRow, CommunityGroupData } from "@/lib/community-data";

function percent(value: number | undefined): string {
  return value === undefined ? "unavailable" : `${(value * 100).toFixed(1)}%`;
}

export function CommunityListing({
  groups,
}: {
  readonly groups: readonly CommunityGroupData[] | null;
}) {
  if (groups === null) {
    return <CommunityListingState title="Community data unavailable" detail="Published community data could not be validated." />;
  }
  if (groups.length === 0) {
    return <CommunityListingState title="No published community models" detail="Published community groups will appear here." />;
  }
  return (
    <section className="grid gap-4" aria-label="Published community model groups">
      {groups.map((group) => {
        const firstVariant = group.variants[0];
        const suffix = group.community_model_group_id.replace("community-group:", "");
        return (
          <article key={group.community_model_group_id} className="rounded border border-bench-line bg-bench-panel p-5">
            <p className="font-mono text-xs uppercase text-bench-accent">Unranked community lane</p>
            <h2 className="mt-2 text-xl font-semibold text-bench-text">
              {firstVariant?.display_name ?? "Community-declared model"}
            </h2>
            <p className="mt-1 font-mono text-xs text-bench-muted">{group.identity_label}</p>
            <div className="mt-4 grid gap-3">
              {group.variants.map((variant) => (
                <div key={variant.artifact_sha256} className="border-l-2 border-bench-line pl-3">
                  <p className="font-mono text-sm text-bench-text">
                    {variant.quant_label ?? "quant unavailable"} · partial {percent(variant.scores.partial_composite)}
                  </p>
                  <p className="mt-1 font-mono text-xs text-bench-muted">
                    measured {percent(variant.scores.measured_headline_weight)} · missing {percent(variant.scores.missing_headline_weight)}
                  </p>
                </div>
              ))}
            </div>
            <Link href={`/community/model/${suffix}`} className="mt-4 inline-block text-sm font-medium text-bench-accent hover:text-bench-text">
              View community record
            </Link>
          </article>
        );
      })}
    </section>
  );
}

export function CommunityListingLive({
  bakedRows,
  groups,
}: {
  readonly bakedRows: readonly CommunityBoardRow[];
  readonly groups: readonly CommunityGroupData[] | null;
}) {
  const state = useLiveCommunityRows(bakedRows);
  return (
    <div className="space-y-3">
      <CommunityFreshness communityUnavailable state={state} />
      {state.kind === "live" ? <CommunityLiveRows rows={state.rows} /> : <CommunityListing groups={groups} />}
    </div>
  );
}

function CommunityLiveRows({ rows }: { readonly rows: readonly CommunityBoardRow[] }) {
  if (rows.length === 0) {
    return <CommunityListingState title="No published community models" detail="Published community groups will appear here." />;
  }
  return (
    <section className="grid gap-4" aria-label="Live community model rows">
      {rows.map((row) => (
        <article key={row.submissionId} className="rounded border border-bench-line bg-bench-panel p-5">
          <p className="font-mono text-xs uppercase text-bench-accent">Unranked community lane</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {row.detailPath === null ? (
              <h2 className="text-xl font-semibold text-bench-text" title="detail page publishes with the next site deploy">
                {row.displayName}
              </h2>
            ) : (
              <h2 className="text-xl font-semibold"><Link href={row.detailPath} className="text-bench-text hover:text-bench-accent">{row.displayName}</Link></h2>
            )}
            <AttributionChip source="community" />
            {row.trust === null || row.trust === undefined ? null : <TrustTierChip trustLabel={row.trust.trust_label} />}
          </div>
          <p className="mt-2 font-mono text-sm text-bench-muted">
            {row.quantLabel ?? "quant unavailable"} · partial {percentNullable(row.partialComposite)}
          </p>
          <p className="mt-1 font-mono text-xs text-bench-muted">
            measured {percentNullable(row.measuredHeadlineWeight)} · missing {percentNullable(row.missingHeadlineWeight)}
          </p>
        </article>
      ))}
    </section>
  );
}

function percentNullable(value: number | null): string {
  return value === null ? "unavailable" : `${(value * 100).toFixed(1)}%`;
}

function CommunityListingState({ title, detail }: { readonly title: string; readonly detail: string }) {
  return (
    <section className="rounded border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">{title}</h2>
      <p className="mt-2 text-sm text-bench-muted">{detail}</p>
    </section>
  );
}

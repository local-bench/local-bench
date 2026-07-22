"use client";

import { useMemo } from "react";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { useLiveCommunityRows } from "@/components/community-live-state";
import { ReplicationTimePanel } from "@/components/replication-time-panel";
import {
  communityBestVariantCandidates,
  selectAcrossBestVariantCandidates,
  type BestVariantCandidate,
} from "@/lib/best-variant";
import type { CommunityArtifactDetail } from "@/lib/community-artifact-details";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { AnchorReference } from "@/lib/data";
import type { FamilyResolutionContext } from "@/lib/family-resolution";

// Landing scatter + benchmarking-time panel over BOTH data sources: baked project runs
// (selected server-side, static per deploy) and live community-envelope rows (refreshed
// client-side by the same hook the ranked table uses). A new submission therefore reaches
// all three landing surfaces on the next page load — no rebake, no redeploy.
export function LandingBestVariantSection({
  anchorRuns,
  bakedCandidates,
  communityArtifactDetails,
  initialCommunityRows,
  resolutionContext,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly bakedCandidates: readonly BestVariantCandidate[];
  readonly communityArtifactDetails: readonly CommunityArtifactDetail[];
  readonly initialCommunityRows: readonly CommunityBoardRow[];
  readonly resolutionContext: FamilyResolutionContext;
}) {
  const liveCommunity = useLiveCommunityRows(initialCommunityRows, true, resolutionContext);
  const points = useMemo(
    () => selectAcrossBestVariantCandidates([
      ...bakedCandidates,
      ...communityBestVariantCandidates(liveCommunity.rows, communityArtifactDetails, resolutionContext),
    ]),
    [bakedCandidates, liveCommunity.rows, communityArtifactDetails, resolutionContext],
  );

  return (
    <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)] xl:items-stretch">
      <BestVariantVramScatter anchorRuns={anchorRuns} points={points} />
      {/* The panel and ranked table share the canonical family resolver: each catalog root
          contributes the same winning measured variant, so hidden fine-tunes cannot leak here. */}
      <ReplicationTimePanel points={points} />
    </div>
  );
}

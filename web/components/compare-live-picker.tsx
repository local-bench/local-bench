"use client";

import { ComparePicker } from "@/components/compare-picker";
import { useLiveCommunityRows } from "@/components/community-live-state";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { CommunityArtifactDetail } from "@/lib/community-artifact-details";
import { getCompareConfigs, type CompareConfig } from "@/lib/compare";
import type { FineTuneComparePreset } from "@/lib/vs-base";

export function CompareLivePicker({
  communityRows,
  communityArtifactDetails,
  fineTunePresets,
  projectConfigs,
}: {
  readonly communityRows: readonly CommunityBoardRow[];
  readonly communityArtifactDetails: readonly CommunityArtifactDetail[];
  readonly fineTunePresets: readonly FineTuneComparePreset[];
  readonly projectConfigs: readonly CompareConfig[];
}) {
  const community = useLiveCommunityRows(communityRows);
  const configs = [...projectConfigs, ...getCompareConfigs(
    [],
    community.rows,
    undefined,
    communityArtifactDetails,
  )];
  return (
    <ComparePicker
      configs={configs}
      fineTunePresets={fineTunePresets}
      initialLeftId={null}
      initialRightId={null}
    />
  );
}

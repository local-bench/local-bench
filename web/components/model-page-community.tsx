"use client";

import { CommunityFamilyResultsLive } from "@/components/community-family-results";
import { useLiveCommunityRows, type LiveCommunityState } from "@/components/community-live-state";
import { ModelBenchTimePanel } from "@/components/model-bench-time-panel";
import { ModelScatter } from "@/components/model-scatter";
import { ModelVariantBoard } from "@/components/model-variant-board";
import type { CommunityBoardRow, CommunityModelTarget } from "@/lib/community-data";
import { communityRowsForModel } from "@/lib/community-family";
import type { AnchorReference, ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "@/lib/data";
import type { FamilyResolutionContext } from "@/lib/family-resolution";
import type { ArtifactProvenanceRegistry } from "@/lib/artifact-provenance";

type ModelPageCommunityProps = {
  readonly anchorRuns: readonly AnchorReference[];
  readonly artifactProvenanceBySha: ArtifactProvenanceRegistry;
  readonly artifactShaByRunId: Record<string, string>;
  readonly bakedRows: readonly CommunityBoardRow[];
  readonly familyModels: readonly ModelFamilyScatterModel[];
  readonly model: ModelDataWithConfiguredAxes;
  readonly resolutionContext: FamilyResolutionContext;
  readonly target: CommunityModelTarget;
};

type ModelPageCommunityViewsProps = Omit<ModelPageCommunityProps, "bakedRows" | "resolutionContext"> & {
  readonly state: LiveCommunityState;
};

export function ModelPageCommunity({
  anchorRuns,
  artifactProvenanceBySha,
  artifactShaByRunId,
  bakedRows,
  familyModels,
  model,
  resolutionContext,
  target,
}: ModelPageCommunityProps) {
  const state = useLiveCommunityRows(bakedRows, true, resolutionContext);
  return <ModelPageCommunityViews
    anchorRuns={anchorRuns}
    artifactProvenanceBySha={artifactProvenanceBySha}
    artifactShaByRunId={artifactShaByRunId}
    familyModels={familyModels}
    model={model}
    state={state}
    target={target}
  />;
}

export function ModelPageCommunityViews({
  anchorRuns,
  artifactProvenanceBySha,
  artifactShaByRunId,
  familyModels,
  model,
  state,
  target,
}: ModelPageCommunityViewsProps) {
  const rows = state.kind === "live" ? communityRowsForModel(state.rows, target) : state.rows;
  return (
    <>
      <ModelScatter
        model={model}
        anchorRuns={anchorRuns}
        communityRows={rows}
        familyModels={familyModels}
      />
      <ModelBenchTimePanel communityRows={rows} model={model} familyModels={familyModels} />
      <ModelVariantBoard
        artifactProvenanceBySha={artifactProvenanceBySha}
        artifactShaByRunId={artifactShaByRunId}
        communityRows={rows}
        familyModels={familyModels}
        model={model}
      />
      <CommunityFamilyResultsLive rows={rows} state={state} />
    </>
  );
}

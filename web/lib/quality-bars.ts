import { clampScore } from "./format";
import type { AnchorReference } from "./data";
import type { RigMatchCandidate } from "./rig-match";

export type AnchorQualityRow = {
  readonly barWidthPercent: number;
  readonly id: string;
  readonly kind: "anchor";
  readonly modelLabel: string;
  readonly score: number;
};

export type LocalQualityRow = {
  readonly barWidthPercent: number;
  readonly demo: boolean;
  readonly id: string;
  readonly kind: "local";
  readonly modelLabel: string;
  readonly quantLabel: string | null;
  readonly score: number;
  readonly vramFootprintGb: number | null;
};

export type QualityRows = {
  readonly anchors: readonly AnchorQualityRow[];
  readonly locals: readonly LocalQualityRow[];
};

export function getRankedQualityRows({
  anchorRuns,
  runs,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly runs: readonly RigMatchCandidate[];
}): QualityRows {
  const anchors = [...anchorRuns].sort(compareAnchors).map((anchor) => ({
    barWidthPercent: clampScore(anchor.composite.point),
    id: anchor.run_id,
    kind: "anchor" as const,
    modelLabel: anchor.model_label,
    score: anchor.composite.point,
  }));
  const localsByModel = new Map<string, RigMatchCandidate>();
  for (const run of runs) {
    if (run.kind !== "community") {
      continue;
    }
    const current = localsByModel.get(run.modelSlug);
    if (current === undefined || isBetterRepresentative(run, current)) {
      localsByModel.set(run.modelSlug, run);
    }
  }
  const locals = [...localsByModel.values()].sort(compareLocalRuns).map((run) => ({
    barWidthPercent: clampScore(run.score.point),
    demo: run.demo,
    id: run.runId,
    kind: "local" as const,
    modelLabel: run.modelLabel,
    quantLabel: run.quantLabel,
    score: run.score.point,
    vramFootprintGb: run.vramFootprintGb,
  }));
  return { anchors, locals };
}

function compareAnchors(left: AnchorReference, right: AnchorReference): number {
  return right.composite.point - left.composite.point || left.model_label.localeCompare(right.model_label);
}

function compareLocalRuns(left: RigMatchCandidate, right: RigMatchCandidate): number {
  return right.score.point - left.score.point || left.modelLabel.localeCompare(right.modelLabel);
}

function isBetterRepresentative(candidate: RigMatchCandidate, current: RigMatchCandidate): boolean {
  const scoreDelta = candidate.score.point - current.score.point;
  if (scoreDelta !== 0) {
    return scoreDelta > 0;
  }
  const candidateVram = candidate.vramFootprintGb ?? Number.POSITIVE_INFINITY;
  const currentVram = current.vramFootprintGb ?? Number.POSITIVE_INFINITY;
  if (candidateVram !== currentVram) {
    return candidateVram < currentVram;
  }
  return quantRank(candidate.quantLabel) < quantRank(current.quantLabel);
}

function quantRank(quantLabel: string | null): number {
  switch (quantLabel) {
    case "FP16":
      return 0;
    case "Q8_0":
      return 1;
    case "Q5_K_M":
      return 2;
    case "Q4_K_M":
      return 3;
    case "Q3_K_M":
      return 4;
    case null:
      return 6;
    default:
      return 5;
  }
}

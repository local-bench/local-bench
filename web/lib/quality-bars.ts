import { clampScore } from "./format";
import { quantRank } from "./quant";
import type { AnchorReference } from "./data";
import type { RigMatchCandidate } from "./rig-match";
import type { AxisScore } from "./schemas";

export type AnchorQualityRow = {
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly barWidthPercent: number;
  readonly id: string;
  readonly kind: "anchor";
  readonly modelLabel: string;
  readonly score: number;
};

export type LocalQualityRow = {
  readonly axes: Readonly<Record<string, AxisScore>>;
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
    axes: anchor.axes,
    barWidthPercent: clampScore(anchor.composite.point),
    id: anchor.run_id,
    kind: "anchor" as const,
    modelLabel: anchor.model_label,
    score: anchor.composite.point,
  }));
  const localsByModel = new Map<string, RigMatchCandidate>();
  for (const run of runs) {
    if (run.kind !== "community" || run.score === null || !run.ranked) {
      continue;
    }
    const current = localsByModel.get(run.modelSlug);
    if (current === undefined || isBetterRepresentative(run, current)) {
      localsByModel.set(run.modelSlug, run);
    }
  }
  const locals = [...localsByModel.values()].sort(compareLocalRuns).map((run) => ({
    axes: run.axes,
    barWidthPercent: clampScore(run.score?.point ?? 0),
    demo: run.demo,
    id: run.runId ?? `${run.modelSlug}:${run.quantLabel ?? "unknown"}`,
    kind: "local" as const,
    modelLabel: run.modelLabel,
    quantLabel: run.quantLabel,
    score: run.score?.point ?? 0,
    vramFootprintGb: run.vramFootprintGb,
  }));
  return { anchors, locals };
}

function compareAnchors(left: AnchorReference, right: AnchorReference): number {
  return right.composite.point - left.composite.point || left.model_label.localeCompare(right.model_label);
}

function compareLocalRuns(left: RigMatchCandidate, right: RigMatchCandidate): number {
  return (right.score?.point ?? 0) - (left.score?.point ?? 0) || left.modelLabel.localeCompare(right.modelLabel);
}

function isBetterRepresentative(candidate: RigMatchCandidate, current: RigMatchCandidate): boolean {
  const scoreDelta = (candidate.score?.point ?? 0) - (current.score?.point ?? 0);
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

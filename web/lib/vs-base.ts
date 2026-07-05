import { AXIS_KEYS, type AxisKey } from "./axis-config";
import type { AxisScore, Score, ScoreStatus } from "./schemas";

export type VsBaseBoardRow = {
  readonly axes: Record<string, AxisScore>;
  readonly bestRunId: string | null;
  readonly composite: Score | null;
  readonly scoreStatus: ScoreStatus;
};

export type VsBaseSide = {
  readonly catalogId: string;
  readonly displayName: string;
  readonly row: VsBaseBoardRow | null;
  readonly slug: string;
};

export type VsBaseAxisDelta = {
  readonly axis: AxisKey;
  readonly base: AxisScore;
  readonly delta: number;
  readonly derivative: AxisScore;
};

export type VsBaseComparison = {
  readonly axes: readonly VsBaseAxisDelta[];
  readonly base: VsBaseSide;
  readonly compareHref: string;
  readonly compositeDelta: number | null;
  readonly derivative: VsBaseSide;
  readonly missing: readonly string[];
};

export type FineTuneComparePreset = {
  readonly leftRunId: string;
  readonly rightRunId: string;
  readonly slug: string;
};

export function buildVsBaseComparison({
  base,
  derivative,
}: {
  readonly base: VsBaseSide;
  readonly derivative: VsBaseSide;
}): VsBaseComparison {
  const measuredBase = measuredRow(base.row);
  const measuredDerivative = measuredRow(derivative.row);
  const axes =
    measuredBase === null || measuredDerivative === null
      ? []
      : AXIS_KEYS.flatMap((axis) => {
          const baseScore = measuredBase.axes[axis];
          const derivativeScore = measuredDerivative.axes[axis];
          if (baseScore === undefined || derivativeScore === undefined) {
            return [];
          }
          return [{ axis, base: baseScore, derivative: derivativeScore, delta: derivativeScore.point - baseScore.point }];
        });

  return {
    axes,
    base,
    compareHref: compareHref(base, derivative),
    compositeDelta:
      measuredBase === null || measuredDerivative === null
        ? null
        : measuredDerivative.composite.point - measuredBase.composite.point,
    derivative,
    missing: [
      ...(measuredBase === null ? ["base not yet benchmarked"] : []),
      ...(measuredDerivative === null ? ["fine-tune not yet benchmarked"] : []),
    ],
  };
}

function measuredRow(row: VsBaseBoardRow | null): (VsBaseBoardRow & { readonly composite: Score }) | null {
  if (row === null || row.scoreStatus !== "measured" || row.composite === null) {
    return null;
  }
  return row as VsBaseBoardRow & { readonly composite: Score };
}

function compareHref(base: VsBaseSide, derivative: VsBaseSide): string {
  if (base.row?.bestRunId !== null && base.row?.bestRunId !== undefined && derivative.row?.bestRunId !== null && derivative.row?.bestRunId !== undefined) {
    return `/compare?left=${encodeURIComponent(derivative.row.bestRunId)}&right=${encodeURIComponent(base.row.bestRunId)}`;
  }
  return `/compare?finetune=${encodeURIComponent(derivative.slug)}`;
}

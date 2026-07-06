import { AXIS_KEYS, type AxisKey } from "./axis-config";
import { HEADLINE_LANE } from "./leaderboard-score";
import type { AxisScore, Score, ScoreStatus } from "./schemas";

export type VsBaseBoardRow = {
  readonly axes: Record<string, AxisScore>;
  readonly bestRunId: string | null;
  readonly composite: Score | null;
  readonly lane: string | null;
  readonly ranked: boolean;
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
    missing: [...missingMessages("base", base), ...missingMessages("fine-tune", derivative)],
  };
}

function missingMessages(side: "base" | "fine-tune", { row }: VsBaseSide): readonly string[] {
  if (measuredRow(row) !== null) {
    return [];
  }
  // A measured row that fails the gate is legacy-lane/unranked data — comparing composites across
  // index versions would manufacture a delta, so we say why the number is withheld instead.
  if (row !== null && row.scoreStatus === "measured" && row.composite !== null) {
    return [`${side} has only previous-index runs — awaiting a current-index rerun`];
  }
  return [`${side} not yet benchmarked`];
}

// Deltas are only honest within the current ranked index: both sides must be measured, ranked, and
// on the headline lane. Legacy-lane composites (previous index versions) never enter a comparison.
function measuredRow(row: VsBaseBoardRow | null): (VsBaseBoardRow & { readonly composite: Score }) | null {
  if (row === null || row.scoreStatus !== "measured" || row.composite === null) {
    return null;
  }
  if (!row.ranked || row.lane !== HEADLINE_LANE) {
    return null;
  }
  return row as VsBaseBoardRow & { readonly composite: Score };
}

export function currentIndexRunId(row: VsBaseBoardRow | null): string | null {
  return measuredRow(row)?.bestRunId ?? null;
}

function compareHref(base: VsBaseSide, derivative: VsBaseSide): string {
  const baseRunId = currentIndexRunId(base.row);
  const derivativeRunId = currentIndexRunId(derivative.row);
  if (baseRunId !== null && derivativeRunId !== null) {
    return `/compare?left=${encodeURIComponent(derivativeRunId)}&right=${encodeURIComponent(baseRunId)}`;
  }
  return `/compare?finetune=${encodeURIComponent(derivative.slug)}`;
}

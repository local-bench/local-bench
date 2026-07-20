import { AXIS_KEYS, type AxisKey } from "./axis-config";
import { HEADLINE_LANE } from "./leaderboard-score";
import { displayDelta } from "./format";
import type { AxisScore, Score, ScoreStatus } from "./schemas";
import { INDEX_VERSION_V3 } from "./scoring-seasons";
import { modelHref } from "./routes";

export type VsBaseBoardRow = {
  readonly axes: Record<string, AxisScore>;
  readonly bestRunId: string | null;
  readonly composite: Score | null;
  readonly diagnosticComposite: Score | null;
  readonly indexVersion?: string | undefined;
  readonly lane: string | null;
  readonly origin?: string | undefined;
  readonly ranked: boolean;
  readonly scoreStatus: ScoreStatus;
  readonly trustLabel?: string | undefined;
};

export type VsBaseSide = {
  readonly catalogId: string;
  readonly displayName: string;
  readonly row: VsBaseBoardRow | null;
  readonly slug: string;
};

export type VsBaseAxisDelta = {
  readonly axis: AxisKey | "tool_use";
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
  const differentScoringSeasons =
    measuredBase !== null &&
    measuredDerivative !== null &&
    indexVersion(measuredBase) !== indexVersion(measuredDerivative);
  const axes =
    measuredBase === null || measuredDerivative === null || differentScoringSeasons
      ? []
      : [...AXIS_KEYS, "tool_use" as const].flatMap((axis) => {
          const baseScore = measuredBase.axes[axis];
          const derivativeScore = measuredDerivative.axes[axis];
          if (baseScore === undefined || derivativeScore === undefined) {
            return [];
          }
          return [{ axis, base: baseScore, derivative: derivativeScore, delta: displayDelta(derivativeScore.point, baseScore.point) }];
        });

  return {
    axes,
    base,
    compareHref: compareHref(base, derivative),
    compositeDelta:
      measuredBase === null || measuredDerivative === null || differentScoringSeasons
        ? null
        : displayDelta(measuredDerivative.composite.point, measuredBase.composite.point),
    derivative,
    missing: differentScoringSeasons
      ? ["different scoring seasons — see bridge"]
      : [...missingMessages("base", base), ...missingMessages("fine-tune", derivative)],
  };
}

function missingMessages(side: "base" | "fine-tune", { row }: VsBaseSide): readonly string[] {
  if (measuredRow(row) !== null) {
    return [];
  }
  // A measured row that fails the gate is legacy-lane/unranked data — comparing composites across
  // index versions would manufacture a delta, so we say why the number is withheld instead.
  if (row !== null && row.scoreStatus === "measured" && (row.composite !== null || row.diagnosticComposite !== null)) {
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
  if (row.lane !== HEADLINE_LANE) {
    return null;
  }
  return row as VsBaseBoardRow & { readonly composite: Score };
}

export function currentIndexRunId(row: VsBaseBoardRow | null): string | null {
  return measuredRow(row)?.bestRunId ?? null;
}

function compareHref(base: VsBaseSide, derivative: VsBaseSide): string {
  if (
    base.row !== null &&
    derivative.row !== null &&
    indexVersion(base.row) !== indexVersion(derivative.row)
  ) {
    return `${modelHref(derivative.slug)}#season-bridge`;
  }
  const baseRunId = currentIndexRunId(base.row);
  const derivativeRunId = currentIndexRunId(derivative.row);
  if (baseRunId !== null && derivativeRunId !== null) {
    return `/compare/?left=${encodeURIComponent(derivativeRunId)}&right=${encodeURIComponent(baseRunId)}`;
  }
  if (hasPreviousIndexDiagnostics(base.row) || hasPreviousIndexDiagnostics(derivative.row)) {
    return modelHref(derivative.slug);
  }
  return `/compare/?finetune=${encodeURIComponent(derivative.slug)}`;
}

function indexVersion(row: VsBaseBoardRow): string {
  return row.indexVersion ?? INDEX_VERSION_V3;
}

function hasPreviousIndexDiagnostics(row: VsBaseBoardRow | null): boolean {
  return (
    row !== null &&
    row.scoreStatus === "measured" &&
    (row.composite !== null || row.diagnosticComposite !== null) &&
    (!row.ranked || row.lane !== HEADLINE_LANE)
  );
}

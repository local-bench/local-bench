import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  type ContextLengthOption,
  type RigMatchCandidate,
} from "./rig-match";
import type { AxisScore, Score } from "./schemas";

export type BestVariantPoint = {
  readonly modelSlug: string;
  readonly modelLabel: string;
  readonly family: string;
  readonly runId: string;
  readonly quantLabel: string | null;
  readonly score: Score;
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly tokS: number | null;
  readonly latencySMedian: number | null;
  readonly wallTimeSeconds: number | null;
  readonly effectiveVramGb: number;
  readonly nRuns: number;
  readonly isFrontier: boolean;
};

// A point is eligible only if it is a real, measured LOCAL model run in the headline scope.
// Anchors (frontier/API references) are drawn as horizontal ceilings, not scatter points;
// demo/missing rows are excluded so the chart never implies precision the data does not have.
// The headline is the capped-thinking scoped view, so other lanes (answer-only diagnostics)
// are excluded here too.
function isEligible(candidate: RigMatchCandidate): boolean {
  return (
    candidate.kind === "community" &&
    !candidate.demo &&
    candidate.scoreStatus === "measured" &&
    candidate.tier?.toLowerCase() === "standard" &&
    candidate.lane === "capped-thinking" &&
    candidate.score !== null &&
    candidate.runId !== null
  );
}

// Best variant WITHIN one model: highest composite, then the cheaper-to-run / faster / more-certain
// run. Mirrors the rig-match ordering intent so the landing chart and the finder agree.
function isBetterWithinModel(candidate: BestVariantPoint, incumbent: BestVariantPoint): boolean {
  if (candidate.score.point !== incumbent.score.point) {
    return candidate.score.point > incumbent.score.point;
  }
  if (candidate.effectiveVramGb !== incumbent.effectiveVramGb) {
    return candidate.effectiveVramGb < incumbent.effectiveVramGb;
  }
  const candidateTokS = candidate.tokS ?? Number.NEGATIVE_INFINITY;
  const incumbentTokS = incumbent.tokS ?? Number.NEGATIVE_INFINITY;
  if (candidateTokS !== incumbentTokS) {
    return candidateTokS > incumbentTokS;
  }
  return candidate.runId.localeCompare(incumbent.runId) < 0;
}

// Efficiency (Pareto) frontier: a point is non-dominated if no other point is at least as good on
// quality AND at least as cheap on VRAM, and strictly better on one of them.
function isDominated(point: BestVariantPoint, others: readonly BestVariantPoint[]): boolean {
  return others.some(
    (other) =>
      other !== point &&
      other.score.point >= point.score.point &&
      other.effectiveVramGb <= point.effectiveVramGb &&
      (other.score.point > point.score.point || other.effectiveVramGb < point.effectiveVramGb),
  );
}

export function selectBestVariantPoints(
  candidates: readonly RigMatchCandidate[],
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): readonly BestVariantPoint[] {
  const bestByModel = new Map<string, BestVariantPoint>();
  for (const candidate of candidates) {
    if (!isEligible(candidate)) {
      continue;
    }
    const vram = estimateVramRequirement(candidate, contextTokens);
    if (vram === null) {
      continue;
    }
    const point: BestVariantPoint = {
      modelSlug: candidate.modelSlug,
      modelLabel: candidate.modelLabel,
      family: candidate.family,
      runId: candidate.runId as string,
      quantLabel: candidate.quantLabel,
      score: candidate.score as Score,
      axes: candidate.axes,
      tokS: candidate.tokS,
      latencySMedian: candidate.latencySMedian,
      wallTimeSeconds: candidate.wallTimeSeconds,
      effectiveVramGb: vram.effectiveRequiredGb,
      nRuns: candidate.nRuns,
      isFrontier: false,
    };
    const incumbent = bestByModel.get(candidate.modelSlug);
    if (incumbent === undefined || isBetterWithinModel(point, incumbent)) {
      bestByModel.set(candidate.modelSlug, point);
    }
  }
  return markFrontier([...bestByModel.values()]);
}

export function markFrontier(points: readonly BestVariantPoint[]): readonly BestVariantPoint[] {
  return points.map((point) => ({ ...point, isFrontier: !isDominated(point, points) }));
}

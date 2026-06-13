import type { Kind, Score } from "./schemas";

export const VRAM_TIERS = [8, 12, 16, 24, 32, 48] as const;
export const QUANT_OPTIONS = ["FP16", "Q8_0", "Q5_K_M", "Q4_K_M", "Q3_K_M"] as const;
export const LANE_FILTERS = ["any", "answer-only"] as const;

export type QuantOption = (typeof QUANT_OPTIONS)[number];
export type QuantFilter = "any" | QuantOption;
export type LaneFilter = (typeof LANE_FILTERS)[number];
export type RigMatchVerdict = "best-under-budget" | "statistical-tie" | "needs-replication" | "not-enough-data";

export type RigMatchAnchor = {
  readonly modelLabel: string;
  readonly score: Score;
};

export type RigMatchCandidate = {
  readonly demo: boolean;
  readonly family: string;
  readonly kind: Kind;
  readonly lane: string | null;
  readonly modelLabel: string;
  readonly modelSlug: string;
  readonly nItems: number;
  readonly nRuns: number;
  readonly quantLabel: string | null;
  readonly runId: string;
  readonly score: Score;
  readonly tokS: number | null;
  readonly vramFootprintGb: number | null;
};

export type RigMatch = RigMatchCandidate & {
  readonly conservativeScore: number;
  readonly frontierGapPercent: number;
  readonly verdict: RigMatchVerdict;
};

export function rankRigMatches({
  anchors,
  candidates,
  lane,
  quant,
  vramGb,
}: {
  readonly anchors: readonly RigMatchAnchor[];
  readonly candidates: readonly RigMatchCandidate[];
  readonly lane: LaneFilter;
  readonly quant: QuantFilter;
  readonly vramGb: number;
}): readonly RigMatch[] {
  const fitted = candidates.filter((candidate) => fitsSelection(candidate, { lane, quant, vramGb })).sort(compareCandidates);
  const bestLowerBound = fitted[0]?.score.lo ?? Number.NEGATIVE_INFINITY;
  return fitted.map((candidate, index) => ({
    ...candidate,
    conservativeScore: candidate.score.lo,
    frontierGapPercent: computeFrontierGapPercent(candidate.score, anchors),
    verdict: verdictFor(candidate, index, bestLowerBound),
  }));
}

export function computeFrontierGapPercent(score: Score, anchors: readonly RigMatchAnchor[]): number {
  const ceiling = Math.max(...anchors.map((anchor) => anchor.score.point), 0);
  return ceiling > 0 ? (score.point / ceiling) * 100 : 0;
}

function fitsSelection(
  candidate: RigMatchCandidate,
  selection: { readonly lane: LaneFilter; readonly quant: QuantFilter; readonly vramGb: number },
): boolean {
  if (candidate.kind === "anchor" || candidate.vramFootprintGb === null) {
    return false;
  }
  if (candidate.vramFootprintGb > selection.vramGb) {
    return false;
  }
  if (selection.quant !== "any" && candidate.quantLabel !== selection.quant) {
    return false;
  }
  return selection.lane === "any" || candidate.lane === selection.lane;
}

function compareCandidates(left: RigMatchCandidate, right: RigMatchCandidate): number {
  return (
    right.score.lo - left.score.lo ||
    right.score.point - left.score.point ||
    nullableNumber(left.vramFootprintGb, Number.POSITIVE_INFINITY) -
      nullableNumber(right.vramFootprintGb, Number.POSITIVE_INFINITY) ||
    nullableNumber(right.tokS, Number.NEGATIVE_INFINITY) - nullableNumber(left.tokS, Number.NEGATIVE_INFINITY) ||
    left.modelLabel.localeCompare(right.modelLabel)
  );
}

function verdictFor(candidate: RigMatchCandidate, index: number, bestLowerBound: number): RigMatchVerdict {
  if (index === 0) {
    return "best-under-budget";
  }
  if (candidate.nItems < 80 || ciHalfWidth(candidate.score) > 4) {
    return "not-enough-data";
  }
  if (candidate.demo || candidate.nRuns < 2) {
    return "needs-replication";
  }
  return candidate.score.hi >= bestLowerBound ? "statistical-tie" : "needs-replication";
}

function ciHalfWidth(score: Score): number {
  return Math.max(Math.abs(score.point - score.lo), Math.abs(score.hi - score.point));
}

function nullableNumber(value: number | null, fallback: number): number {
  return value ?? fallback;
}

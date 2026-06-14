import type { Kind, Score } from "./schemas";
import { quantBytesPerParam } from "./quant";
import type { QuantFilter } from "./quant";

export const VRAM_TIERS = [8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512] as const;
export const LANE_FILTERS = ["any", "answer-only"] as const;
export const CONTEXT_LENGTH_OPTIONS = [8192, 32768, 131072] as const;
export const DEFAULT_CONTEXT_TOKENS: ContextLengthOption = 8192;
export const RUNTIME_OVERHEAD_GB = 1.5;
export { QUANT_OPTIONS, isQuantOption, quantBytesPerParam, quantOrder, quantRank, toQuantFilter } from "./quant";
export type { QuantFilter, QuantOption } from "./quant";

const KV_CACHE_GB_PER_BILLION_PARAMS_AT_8K = 0.03;

export type LaneFilter = (typeof LANE_FILTERS)[number];
export type ContextLengthOption = (typeof CONTEXT_LENGTH_OPTIONS)[number];
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
  readonly vramEstimate: VramEstimate;
};

export type VramEstimate = {
  readonly contextTokens: ContextLengthOption;
  readonly effectiveRequiredGb: number;
  readonly kvCacheGb: number;
  readonly overheadGb: number;
  readonly parameterBillionEstimate: number;
  readonly weightsGb: number;
};

type FittedCandidate = {
  readonly candidate: RigMatchCandidate;
  readonly vramEstimate: VramEstimate;
};

export function rankRigMatches({
  anchors,
  candidates,
  contextTokens = DEFAULT_CONTEXT_TOKENS,
  lane,
  quant,
  vramGb,
}: {
  readonly anchors: readonly RigMatchAnchor[];
  readonly candidates: readonly RigMatchCandidate[];
  readonly contextTokens?: ContextLengthOption;
  readonly lane: LaneFilter;
  readonly quant: QuantFilter;
  readonly vramGb: number;
}): readonly RigMatch[] {
  const fitted = candidates
    .flatMap((candidate) => toFittedCandidate(candidate, { contextTokens, lane, quant, vramGb }))
    .sort(compareFittedCandidates);
  const bestLowerBound = fitted[0]?.candidate.score.lo ?? Number.NEGATIVE_INFINITY;
  return fitted.map(({ candidate, vramEstimate }, index) => ({
    ...candidate,
    conservativeScore: candidate.score.lo,
    frontierGapPercent: computeFrontierGapPercent(candidate.score, anchors),
    verdict: verdictFor(candidate, index, bestLowerBound),
    vramEstimate,
  }));
}

export function computeFrontierGapPercent(score: Score, anchors: readonly RigMatchAnchor[]): number {
  const ceiling = Math.max(...anchors.map((anchor) => anchor.score.point), 0);
  return ceiling > 0 ? (score.point / ceiling) * 100 : 0;
}

export function estimateVramRequirement(
  candidate: Pick<RigMatchCandidate, "quantLabel" | "vramFootprintGb">,
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): VramEstimate | null {
  if (candidate.vramFootprintGb === null) {
    return null;
  }

  const parameterBillionEstimate = candidate.vramFootprintGb / quantBytesPerParam(candidate.quantLabel);
  const contextMultiplier = contextTokens / DEFAULT_CONTEXT_TOKENS;
  const kvCacheGb = parameterBillionEstimate * KV_CACHE_GB_PER_BILLION_PARAMS_AT_8K * contextMultiplier;
  return {
    contextTokens,
    effectiveRequiredGb: candidate.vramFootprintGb + kvCacheGb + RUNTIME_OVERHEAD_GB,
    kvCacheGb,
    overheadGb: RUNTIME_OVERHEAD_GB,
    parameterBillionEstimate,
    weightsGb: candidate.vramFootprintGb,
  };
}

export function findMinimumVramTier(requiredGb: number): number | null {
  return VRAM_TIERS.find((tier) => tier >= requiredGb) ?? null;
}

export function formatContextLength(value: ContextLengthOption): string {
  switch (value) {
    case 8192:
      return "8K";
    case 32768:
      return "32K";
    case 131072:
      return "128K";
    default:
      return "8K";
  }
}

function toFittedCandidate(
  candidate: RigMatchCandidate,
  selection: {
    readonly contextTokens: ContextLengthOption;
    readonly lane: LaneFilter;
    readonly quant: QuantFilter;
    readonly vramGb: number;
  },
): readonly FittedCandidate[] {
  const vramEstimate = estimateVramRequirement(candidate, selection.contextTokens);
  if (vramEstimate === null) {
    return [];
  }
  return fitsSelection(candidate, selection, vramEstimate) ? [{ candidate, vramEstimate }] : [];
}

function fitsSelection(
  candidate: RigMatchCandidate,
  selection: { readonly lane: LaneFilter; readonly quant: QuantFilter; readonly vramGb: number },
  vramEstimate: VramEstimate,
): boolean {
  if (candidate.kind === "anchor") {
    return false;
  }
  if (vramEstimate.effectiveRequiredGb > selection.vramGb) {
    return false;
  }
  if (selection.quant !== "any" && candidate.quantLabel !== selection.quant) {
    return false;
  }
  return selection.lane === "any" || candidate.lane === selection.lane;
}

function compareFittedCandidates(left: FittedCandidate, right: FittedCandidate): number {
  return (
    right.candidate.score.lo - left.candidate.score.lo ||
    right.candidate.score.point - left.candidate.score.point ||
    left.vramEstimate.effectiveRequiredGb - right.vramEstimate.effectiveRequiredGb ||
    nullableNumber(right.candidate.tokS, Number.NEGATIVE_INFINITY) -
      nullableNumber(left.candidate.tokS, Number.NEGATIVE_INFINITY) ||
    left.candidate.modelLabel.localeCompare(right.candidate.modelLabel)
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

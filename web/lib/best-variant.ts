import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  type ContextLengthOption,
  type RigMatchCandidate,
} from "./rig-match";
import { HEADLINE_LANE } from "./leaderboard-score";
import {
  buildFamilyResolutionContext,
  familyResolutionKey,
  resolveFamily,
  type FamilyResolution,
  type FamilyResolutionContext,
} from "./family-resolution";
import { selectBestPerFamily } from "./landing-best-per-base";
import type { AxisScore, CatalogModel, ConformanceGates, Score } from "./schemas";

export type BestVariantPoint = {
  readonly modelSlug: string;
  readonly modelLabel: string;
  readonly family: string;
  readonly weightsFamilyKey?: string;
  readonly weightsFamilyLabel?: string;
  readonly weightsFamilySlug?: string | null;
  readonly runId: string;
  readonly quantLabel: string | null;
  readonly score: Score;
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly conformanceGates?: ConformanceGates;
  readonly tokS: number | null;
  readonly latencySMedian: number | null;
  readonly wallTimeSeconds: number | null;
  readonly effectiveVramGb: number;
  readonly nRuns: number;
  readonly isFrontier: boolean;
};

export type BestVariantSelectionOptions = {
  readonly catalogModels?: readonly CatalogModel[];
  readonly contextTokens?: ContextLengthOption;
};

type EligibleRigMatchCandidate = RigMatchCandidate & {
  readonly runId: string;
  readonly score: Score;
};

// A point is eligible only if it is a real, measured LOCAL model run in the headline scope.
// Anchors (frontier/API references) are drawn as horizontal ceilings, not scatter points;
// demo/missing rows are excluded so the chart never implies precision the data does not have.
// The headline is the bounded-final lane scoped view, so other lanes (legacy capped-thinking,
// answer-only diagnostics) are excluded here too.
function isEligible(candidate: RigMatchCandidate): candidate is EligibleRigMatchCandidate {
  return (
    candidate.kind === "community" &&
    !candidate.demo &&
    candidate.scoreStatus === "measured" &&
    candidate.lane === HEADLINE_LANE &&
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
  options: BestVariantSelectionOptions = {},
): readonly BestVariantPoint[] {
  const resolutionContext = buildFamilyResolutionContext(options.catalogModels ?? []);
  return selectBestPoints(candidates, options.contextTokens ?? DEFAULT_CONTEXT_TOKENS, (candidate) =>
    familyRootForCandidate(candidate, resolutionContext),
  );
}

function selectBestPoints(
  candidates: readonly RigMatchCandidate[],
  contextTokens: ContextLengthOption,
  rootForCandidate: (candidate: EligibleRigMatchCandidate) => ResolvedFamilyRoot,
): readonly BestVariantPoint[] {
  const bestByModel = new Map<string, { readonly point: BestVariantPoint; readonly resolution: FamilyResolution }>();
  for (const candidate of candidates) {
    if (!isEligible(candidate)) {
      continue;
    }
    // Measured rows carry the benchmarked artifact's real on-disk size (vramFootprintGb,
    // from the run record). Catalog vram_gb_8k estimates describe whatever GGUF repo the
    // catalog references — potentially a different build with different units — and must
    // never outrank measured reality here: they inverted the Qwen/Qwopus frontier on
    // 2026-07-08 (catalog said Qwopus was 1.4 GB cheaper; the measured files say the
    // opposite). Force the measured-footprint estimate whenever a footprint exists.
    const vram = estimateVramRequirement(
      candidate.vramFootprintGb !== null ? { ...candidate, vramRequiredGb8k: null } : candidate,
      contextTokens,
    );
    if (vram === null) {
      continue;
    }
    const weightsFamilyRoot = rootForCandidate(candidate);
    const pointBase = {
      modelSlug: candidate.modelSlug,
      modelLabel: candidate.modelLabel,
      family: candidate.family,
      weightsFamilyKey: weightsFamilyRoot.key,
      weightsFamilyLabel: weightsFamilyRoot.label,
      weightsFamilySlug: weightsFamilyRoot.slug,
      runId: candidate.runId,
      quantLabel: candidate.quantLabel,
      score: candidate.score,
      axes: candidate.axes,
      tokS: candidate.tokS,
      latencySMedian: candidate.latencySMedian,
      wallTimeSeconds: candidate.wallTimeSeconds,
      effectiveVramGb: vram.effectiveRequiredGb,
      nRuns: candidate.nRuns,
      isFrontier: false,
    };
    const point: BestVariantPoint =
      candidate.conformanceGates === undefined
        ? pointBase
        : { ...pointBase, conformanceGates: candidate.conformanceGates };
    const incumbent = bestByModel.get(candidate.modelSlug);
    if (incumbent === undefined || isBetterWithinModel(point, incumbent.point)) {
      bestByModel.set(candidate.modelSlug, { point, resolution: weightsFamilyRoot.resolution });
    }
  }
  const selected = selectBestPerFamily([...bestByModel.values()].map((candidate) => ({
    displayedComposite: candidate.point.score.point,
    resolution: candidate.resolution,
    source: "maintainer" as const,
    value: candidate.point,
  })));
  return markFrontier(selected.map((candidate) => candidate.value));
}

type ResolvedFamilyRoot = {
  readonly key: string;
  readonly label: string;
  readonly resolution: FamilyResolution;
  readonly slug: string | null;
};

function familyRootForCandidate(
  candidate: EligibleRigMatchCandidate,
  context: FamilyResolutionContext,
): ResolvedFamilyRoot {
  const resolution = resolveFamily({
    catalog_id: null,
    family: candidate.family,
    model_label: candidate.modelLabel,
    slug: candidate.modelSlug,
  }, context);
  const rootEntry = context.catalog.find((entry) => entry.catalogId === resolution.rootCatalogId);
  return {
    key: familyResolutionKey(resolution) ?? candidate.modelSlug,
    label: rootEntry?.displayName ?? resolution.familyLabel ?? candidate.modelLabel,
    resolution,
    slug: resolution.rootSlug ?? candidate.modelSlug,
  };
}

export function markFrontier(points: readonly BestVariantPoint[]): readonly BestVariantPoint[] {
  return points.map((point) => ({ ...point, isFrontier: !isDominated(point, points) }));
}

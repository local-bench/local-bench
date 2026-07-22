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
import { selectBestPerFamily, type FamilyRankedSource } from "./landing-best-per-base";
import {
  communityArtifactDetailForSha,
  type CommunityArtifactDetail,
} from "./community-artifact-details";
import type { CommunityBoardRow } from "./community-data";
import { communityDisplayAxes, communityScore } from "./community-scores";
import { formatGpuShort } from "./format";
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
  // Set only for live community-envelope rows benchmarked off the reference rig; baked
  // project runs leave it null (reference rig implied).
  readonly hardwareLabel?: string | null;
};

// A pre-collapse candidate: one best point per model, still carrying its family resolution so
// baked and live sources can be merged through the SAME selectBestPerFamily pass the ranked
// table uses — the panel/scatter and the table must never disagree on a family's winner.
export type BestVariantCandidate = {
  readonly point: BestVariantPoint;
  readonly resolution: FamilyResolution;
  readonly source: FamilyRankedSource;
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
  return selectAcrossBestVariantCandidates(bakedBestVariantCandidates(candidates, options));
}

// Collapse merged baked + live candidates to one winner per base family and mark the
// efficiency frontier. Tie-break prefers the maintainer row, mirroring the ranked table.
export function selectAcrossBestVariantCandidates(
  candidates: readonly BestVariantCandidate[],
): readonly BestVariantPoint[] {
  const selected = selectBestPerFamily(candidates.map((candidate) => ({
    displayedComposite: candidate.point.score.point,
    resolution: candidate.resolution,
    source: candidate.source,
    value: candidate.point,
  })));
  return markFrontier(selected.map((candidate) => candidate.value));
}

export function bakedBestVariantCandidates(
  candidates: readonly RigMatchCandidate[],
  options: BestVariantSelectionOptions = {},
): readonly BestVariantCandidate[] {
  const resolutionContext = buildFamilyResolutionContext(options.catalogModels ?? []);
  return selectBestPoints(candidates, options.contextTokens ?? DEFAULT_CONTEXT_TOKENS, (candidate) =>
    familyRootForCandidate(candidate, resolutionContext),
  );
}

// One point per live envelope row that carries everything the landing visualizations need.
// Mirrors the model-page scatter's eligibility rule: a complete headline composite plus a
// catalog-joined artifact (the VRAM axis has no honest value without the artifact's size).
export function communityBestVariantCandidates(
  rows: readonly CommunityBoardRow[],
  artifactDetails: readonly CommunityArtifactDetail[],
  context: FamilyResolutionContext,
): readonly BestVariantCandidate[] {
  return rows.flatMap((row) => {
    if (!row.headlineComplete || row.compositeFull === null) return [];
    const detail = communityArtifactDetailForSha(artifactDetails, row.artifactSha256);
    if (detail === undefined || detail.vramGb8k === null) return [];
    const resolution = resolveFamily(row, context);
    const rootEntry = context.catalog.find((entry) => entry.catalogId === resolution.rootCatalogId);
    const gpuName = row.hardware?.gpu_name;
    const point: BestVariantPoint = {
      modelSlug: detail.slug,
      modelLabel: detail.modelLabel,
      family: row.familyLabel ?? row.catalogFamily ?? row.family ?? detail.modelLabel,
      weightsFamilyKey: familyResolutionKey(resolution) ?? row.artifactSha256,
      weightsFamilyLabel: rootEntry?.displayName ?? resolution.familyLabel ?? detail.modelLabel,
      weightsFamilySlug: resolution.rootSlug ?? detail.slug,
      runId: row.submissionId,
      quantLabel: detail.quantLabel ?? row.quantLabel,
      score: communityScore(row.compositeFull),
      axes: communityDisplayAxes(row),
      // overall_tps = completion tokens over total wall time — the closest live analog of the
      // baked runs' effective tok/s. Decode-only tps would overstate against baked rows.
      tokS: row.perf?.overall_tps ?? null,
      latencySMedian: row.perf?.latency_s_median ?? null,
      wallTimeSeconds: row.perf?.wall_time_seconds ?? null,
      // Artifact-formula estimate at 8k, same family as the catalog figures the scatter's
      // baked shells use; live rows have no measured runtime footprint field to prefer.
      effectiveVramGb: detail.vramGb8k,
      nRuns: 1,
      isFrontier: false,
      hardwareLabel: gpuName === null || gpuName === undefined || gpuName === ""
        ? null
        : formatGpuShort({ name: gpuName, vram_gb: row.hardware?.vram_gb ?? null }),
    };
    return [{
      point,
      resolution,
      source: row.origin === "project_anchor" ? "maintainer" as const : "community" as const,
    }];
  });
}

function selectBestPoints(
  candidates: readonly RigMatchCandidate[],
  contextTokens: ContextLengthOption,
  rootForCandidate: (candidate: EligibleRigMatchCandidate) => ResolvedFamilyRoot,
): readonly BestVariantCandidate[] {
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
  return [...bestByModel.values()].map((candidate) => ({
    point: candidate.point,
    resolution: candidate.resolution,
    source: "maintainer" as const,
  }));
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

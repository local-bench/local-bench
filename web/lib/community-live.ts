import {
  adaptLegacyBoardRow,
  parseBoardEnvelope,
  type AdaptedBoardRow,
  type LiveBoardRow,
  type ParsedBoardEnvelope,
} from "./board-adapter";
import { normalizeCommunityCoverage } from "./community-coverage";
import type { CommunityBoardRow } from "./community-data";
import { communityRowsWithFamilyPaths } from "./community-family";
import {
  EMPTY_FAMILY_RESOLUTION_CONTEXT,
  type FamilyResolutionContext,
} from "./family-resolution";

export type { LiveBoardRow } from "./board-adapter";

export function parseCommunityLiveBoard(value: unknown): ParsedBoardEnvelope | null {
  return parseBoardEnvelope(value);
}

export function reconcileCommunityRows(
  baked: readonly CommunityBoardRow[],
  live: readonly (AdaptedBoardRow | LiveBoardRow)[],
  resolutionContext: FamilyResolutionContext = EMPTY_FAMILY_RESOLUTION_CONTEXT,
): readonly CommunityBoardRow[] {
  const bakedBySubmission = new Map(baked.map((row) => [row.submissionId, row]));
  const merged = live
    .map((row): AdaptedBoardRow => isAdaptedBoardRow(row) ? row : adaptLegacyBoardRow(row))
    .filter((row) => row.origin === "community" || row.origin === "project_anchor")
    .map((row) => mergeCommunityRow(bakedBySubmission.get(row.submissionId), row));
  return communityRowsWithFamilyPaths(merged, resolutionContext);
}

function mergeCommunityRow(
  baked: CommunityBoardRow | undefined,
  live: AdaptedBoardRow,
): CommunityBoardRow {
  const hardware = live.hardware ?? baked?.hardware;
  const perf = live.perf ?? baked?.perf;
  const runtime = live.runtime ?? baked?.runtime;
  const coverage = normalizeCommunityCoverage(
    live.measuredHeadlineWeight ?? measuredWeight(live),
    live.missingHeadlineWeight ?? (live.headlineComplete ? 0 : baked?.missingHeadlineWeight ?? null),
  );
  return {
    artifactSha256: live.artifactSha256,
    axes: live.axes,
    ...(baked?.catalogFamily === undefined ? {} : { catalogFamily: baked.catalogFamily }),
    ...(live.communityModelGroupId === undefined ? {} : { communityModelGroupId: live.communityModelGroupId }),
    compositeFull: live.compositeFull,
    declaredBaseModels: baked?.declaredBaseModels ?? live.declaredBaseModels,
    detailPath: null,
    displayName: live.displayName,
    family: live.family,
    globalRank: live.globalRank,
    ...(hardware === undefined ? {} : { hardware }),
    headlineComplete: live.headlineComplete,
    identityLabel: baked?.identityLabel ?? "community-declared, identity-unverified",
    indexVersion: live.indexVersion,
    lineage: baked?.lineage ?? live.lineageEnrichment,
    ...coverage,
    origin: "community",
    partialComposite: live.compositeFull ?? baked?.partialComposite ?? null,
    ...(perf === undefined ? {} : { perf }),
    quantLabel: live.quantLabel,
    ranked: live.ranked,
    ...(runtime === undefined ? {} : { runtime }),
    submissionId: live.submissionId,
    submitterDisplayName: live.submitterDisplayName,
    submitterGithubLogin: live.submitterGithubLogin,
    submitterKeyFingerprint: live.submitterKeyFingerprint,
    ...(live.timestamps === null ? {} : { timestamps: live.timestamps }),
    ...(live.trust === undefined ? {} : { trust: live.trust }),
  };
}

function isAdaptedBoardRow(row: AdaptedBoardRow | LiveBoardRow): row is AdaptedBoardRow {
  return "artifactSha256" in row;
}

function measuredWeight(row: AdaptedBoardRow): number | null {
  if (row.headlineComplete) return 1;
  const measured = Object.values(row.axes).filter((axis) => axis.status === "measured").length;
  return measured === 0 ? null : measured / 6;
}

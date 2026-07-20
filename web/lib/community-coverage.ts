// Client-safe coverage normalization. This module must stay free of node:*
// imports: it is bundled into client components via community-live.ts, while
// community-data.ts (which also consumes it) is server-only (node:fs).
export type CommunityCoverageProjection = {
  readonly coverageConsistent?: boolean;
  readonly measuredHeadlineWeight: number | null;
  readonly missingHeadlineWeight: number | null;
};

const COVERAGE_ROUNDING_TOLERANCE = 0.02;

export function normalizeCommunityCoverage(
  measuredHeadlineWeight: number | null,
  missingHeadlineWeight: number | null,
): CommunityCoverageProjection {
  const shares = { measuredHeadlineWeight, missingHeadlineWeight };
  if (measuredHeadlineWeight === null || missingHeadlineWeight === null) return shares;
  const coverageConsistent = Math.abs(measuredHeadlineWeight + missingHeadlineWeight - 1)
    <= COVERAGE_ROUNDING_TOLERANCE + Number.EPSILON;
  return {
    coverageConsistent,
    measuredHeadlineWeight,
    missingHeadlineWeight: coverageConsistent ? 1 - measuredHeadlineWeight : missingHeadlineWeight,
  };
}

export type TrustPopulationRow = {
  readonly origin?: string | undefined;
  readonly ranked: boolean;
  readonly trust_label?: string | undefined;
};

/** The only population allowed to affect ranks, representatives, identity, or provenance. */
export function isTrustedRankedPopulation(row: TrustPopulationRow): boolean {
  return row.ranked && row.origin === "project_anchor" && row.trust_label === "project_anchor";
}

export function isTrustedPopulation(row: Omit<TrustPopulationRow, "ranked">): boolean {
  return row.origin === "project_anchor" && row.trust_label === "project_anchor";
}

export function selectTrustedHeaderSource<T extends TrustPopulationRow>(rows: readonly T[]): T | undefined {
  return rows.find(isTrustedRankedPopulation);
}

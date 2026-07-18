import type { CommunityBoardRow, CommunityModelTarget } from "./community-data";

export function communityRowsForModel(
  rows: readonly CommunityBoardRow[],
  target: CommunityModelTarget,
): readonly CommunityBoardRow[] {
  const familyKey = normalizedFamily(target.family);
  return rows.filter((row) => {
    const lineage = row.lineage;
    const repositories = lineage === undefined
      ? [...(row.declaredBaseModels ?? [])]
      : [lineage.repo.id, ...lineage.card_declared_edges.flatMap((edge) => [edge.base, edge.child])];
    if (repositories.length === 0) return false;
    if (
      target.catalogId !== null
      && target.catalogId !== undefined
      && repositories.some((repoId) => repoId === target.catalogId)
    ) return true;
    return familyKey.length > 0 && repositories.some((repoId) => {
      const repoName = repoId.split("/").at(-1) ?? repoId;
      return normalizedFamily(repoName).includes(familyKey);
    });
  });
}

function normalizedFamily(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "");
}

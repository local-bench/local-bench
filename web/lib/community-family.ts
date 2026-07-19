import type { CommunityBoardRow, CommunityModelTarget } from "./community-data";
import type { IndexModel } from "./schemas";

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
    if (target.catalogId !== null && target.catalogId !== undefined) {
      return repositories.some((repoId) => repoId === target.catalogId);
    }
    return familyKey.length > 0 && repositories.some((repoId) => {
      const repoName = repoId.split("/").at(-1) ?? repoId;
      return normalizedFamily(repoName).includes(familyKey);
    });
  });
}

export function communityRowCatalogIds(rows: readonly CommunityBoardRow[]): ReadonlySet<string> {
  return new Set(rows.flatMap((row) => {
    if (row.lineage === undefined) return row.declaredBaseModels ?? [];
    return [
      row.lineage.repo.id,
      ...row.lineage.card_declared_edges.flatMap((edge) => [edge.base, edge.child]),
    ];
  }));
}

export function communityRowsWithFamilyPaths(
  rows: readonly CommunityBoardRow[],
  models: readonly IndexModel[],
): readonly CommunityBoardRow[] {
  return rows.map((row) => {
    const model = models.find((candidate) => communityRowsForModel([row], {
      catalogId: candidate.catalog_id,
      family: candidate.family,
    }).length > 0) ?? models.find((candidate) => candidate.family === row.family);
    return model === undefined ? row : { ...row, detailPath: `/model/${model.slug}` };
  });
}

function normalizedFamily(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "");
}

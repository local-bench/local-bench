import type { CommunityBoardRow, CommunityModelTarget } from "./community-data";
import type { IndexModel } from "./schemas";

type CommunityCatalogModel = Pick<IndexModel, "catalog_id" | "family" | "model_label" | "slug"> & {
  readonly artifactSha256s?: readonly string[];
};

export function communityRowsForModel(
  rows: readonly CommunityBoardRow[],
  target: CommunityModelTarget,
): readonly CommunityBoardRow[] {
  return rows.filter((row) => {
    if (target.artifactSha256s?.includes(row.artifactSha256) === true) return true;
    if (matchesLineage(row, target)) return true;
    return matchesExactModelName(row, target);
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
  models: readonly CommunityCatalogModel[],
): readonly CommunityBoardRow[] {
  return rows.map((row) => {
    const model = models.find((candidate) => candidate.artifactSha256s?.includes(row.artifactSha256) === true)
      ?? models.find((candidate) => matchesLineage(row, targetFor(candidate)))
      ?? models.find((candidate) => matchesFamily(row, candidate.family))
      ?? models.find((candidate) => matchesExactModelName(row, targetFor(candidate)));
    return model === undefined
      ? row
      : { ...row, catalogFamily: model.family, detailPath: `/model/${model.slug}` };
  });
}

function targetFor(model: CommunityCatalogModel): CommunityModelTarget {
  return {
    catalogId: model.catalog_id,
    family: model.family,
    modelLabel: model.model_label,
    slug: model.slug,
    ...(model.artifactSha256s === undefined ? {} : { artifactSha256s: model.artifactSha256s }),
  };
}

function matchesLineage(row: CommunityBoardRow, target: CommunityModelTarget): boolean {
  const repositories = repositoriesFor(row);
  if (repositories.length === 0) return false;
  if (target.catalogId !== null && target.catalogId !== undefined) {
    return repositories.some((repoId) => repoId === target.catalogId);
  }
  const familyKey = normalizedFamily(target.family);
  return familyKey.length > 0 && repositories.some((repoId) => {
    const repoName = repoId.split("/").at(-1) ?? repoId;
    return normalizedFamily(repoName).includes(familyKey);
  });
}

function repositoriesFor(row: CommunityBoardRow): readonly string[] {
  const lineage = row.lineage;
  return lineage === undefined
    ? row.declaredBaseModels ?? []
    : [lineage.repo.id, ...lineage.card_declared_edges.flatMap((edge) => [edge.base, edge.child])];
}

function matchesFamily(row: CommunityBoardRow, family: string): boolean {
  return row.family !== null
    && normalizedFamily(family).length > 0
    && normalizedFamily(row.family) === normalizedFamily(family);
}

function matchesExactModelName(row: CommunityBoardRow, target: CommunityModelTarget): boolean {
  const displayName = normalizedFamily(row.displayName);
  return displayName.length > 0 && [target.slug, target.modelLabel]
    .some((candidate) => candidate !== undefined && normalizedFamily(candidate) === displayName);
}

function normalizedFamily(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "");
}

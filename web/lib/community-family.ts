import type { CommunityBoardRow, CommunityModelTarget } from "./community-data";
import {
  familyCatalogEntryForArtifactSha,
  overlayLineageForArtifactSha,
  resolveFamily,
  type FamilyResolutionContext,
} from "./family-resolution";
import type { IndexModel } from "./schemas";
import { modelHref } from "./routes";

type CommunityCatalogModel = Pick<IndexModel, "catalog_id" | "family" | "model_label" | "slug"> & {
  readonly artifactSha256s?: readonly string[];
};

export function communityRowsForModel(
  rows: readonly CommunityBoardRow[],
  target: CommunityModelTarget,
): readonly CommunityBoardRow[] {
  return rows.filter((row) => {
    if (target.artifactSha256s?.includes(row.artifactSha256) === true) return true;
    if (target.catalogId !== null
      && target.catalogId !== undefined
      && row.chainCatalogIds?.includes(target.catalogId) === true) return true;
    return matchesExactModelName(row, target);
  });
}

export function communityRowCatalogIds(rows: readonly CommunityBoardRow[]): ReadonlySet<string> {
  return new Set(rows.flatMap((row) => row.chainCatalogIds ?? []));
}

export function communityRowsWithFamilyPaths(
  rows: readonly CommunityBoardRow[],
  contextOrModels: FamilyResolutionContext | readonly CommunityCatalogModel[],
): readonly CommunityBoardRow[] {
  const context = "catalog" in contextOrModels
    ? contextOrModels
    : compatibilityContext(contextOrModels);
  return rows.map((row) => {
    const resolution = resolveFamily(row, context);
    const artifactEntry = familyCatalogEntryForArtifactSha(row.artifactSha256, context);
    const overlayLineage = overlayLineageForArtifactSha(row.artifactSha256, context);
    return {
      ...row,
      ...(resolution.familyLabel === null ? {} : { catalogFamily: resolution.familyLabel }),
      chainCatalogIds: resolution.chainCatalogIds,
      confidence: resolution.confidence,
      detailPath: artifactEntry === undefined ? null : modelHref(artifactEntry.slug),
      familyLabel: resolution.familyLabel,
      lineage: overlayLineage ?? row.lineage,
      rootCatalogId: resolution.rootCatalogId,
      rootSlug: resolution.rootSlug,
    };
  });
}

function compatibilityContext(models: readonly CommunityCatalogModel[]): FamilyResolutionContext {
  return {
    catalog: models.map((model) => {
      const catalogId = model.catalog_id ?? model.slug;
      return {
        artifactSha256s: model.artifactSha256s ?? [],
        catalogId,
        chainCatalogIds: [catalogId],
        displayName: model.model_label,
        familyLabel: model.family,
        rootCatalogId: catalogId,
        rootSlug: model.slug,
        slug: model.slug,
      };
    }),
    overlay: [],
  };
}

function matchesExactModelName(row: CommunityBoardRow, target: CommunityModelTarget): boolean {
  const displayName = normalizedIdentity(row.displayName);
  return displayName.length > 0 && [target.slug, target.modelLabel]
    .some((candidate) => candidate !== undefined && normalizedIdentity(candidate) === displayName);
}

function normalizedIdentity(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "");
}

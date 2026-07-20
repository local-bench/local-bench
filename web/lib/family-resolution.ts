import {
  catalogLineageChainEntries,
  catalogModelMap,
} from "./catalog-lineage";
import type { CommunityBoardRow, CommunityLineage } from "./community-data";
import type { CatalogModel, IndexModel } from "./schemas";

export type FamilyResolutionConfidence =
  | "artifact-sha"
  | "lineage"
  | "declared-family"
  | "exact-name"
  | null;

export type FamilyResolution = {
  readonly chainCatalogIds: readonly string[];
  readonly confidence: FamilyResolutionConfidence;
  readonly familyLabel: string | null;
  readonly rootCatalogId: string | null;
  readonly rootSlug: string | null;
};

export type FamilyResolutionIndexModel = Pick<
  IndexModel,
  "catalog_id" | "family" | "model_label"
> & {
  readonly artifactSha256s?: readonly string[];
  readonly slug: string;
};

export type FamilyResolutionCatalogEntry = {
  readonly artifactSha256s: readonly string[];
  readonly catalogId: string;
  readonly chainCatalogIds: readonly string[];
  readonly displayName: string;
  readonly familyLabel: string;
  readonly rootCatalogId: string;
  readonly rootSlug: string;
  readonly slug: string;
};

export type FamilyResolutionOverlayEntry = {
  readonly artifactSha256: string;
  readonly lineage: CommunityLineage;
};

export type FamilyResolutionContext = {
  readonly catalog: readonly FamilyResolutionCatalogEntry[];
  readonly overlay: readonly FamilyResolutionOverlayEntry[];
};

export const EMPTY_FAMILY_RESOLUTION_CONTEXT: FamilyResolutionContext = {
  catalog: [],
  overlay: [],
};

export function buildFamilyResolutionContext(
  catalogModels: readonly CatalogModel[],
  indexModels: readonly FamilyResolutionIndexModel[] = [],
  overlay: ReadonlyMap<string, CommunityLineage> = new Map(),
): FamilyResolutionContext {
  const byId = catalogModelMap(catalogModels);
  const indexArtifactsByCatalogId = new Map<string, readonly string[]>();
  const indexArtifactsBySlug = new Map<string, readonly string[]>();
  for (const model of indexModels) {
    if (model.artifactSha256s === undefined) continue;
    if (model.catalog_id !== null && model.catalog_id !== undefined) {
      indexArtifactsByCatalogId.set(model.catalog_id, model.artifactSha256s);
    }
    indexArtifactsBySlug.set(model.slug, model.artifactSha256s);
  }
  return {
    catalog: catalogModels.map((model) => {
      const chain = catalogLineageChainEntries(model, byId);
      const root = chain.at(-1) ?? model;
      const artifactSha256s = new Set([
        ...catalogArtifactSha256s(model),
        ...(indexArtifactsByCatalogId.get(model.id) ?? []),
        ...(indexArtifactsBySlug.get(model.slug) ?? []),
      ]);
      return {
        artifactSha256s: [...artifactSha256s],
        catalogId: model.id,
        chainCatalogIds: chain.map((entry) => entry.id),
        displayName: model.display_name,
        familyLabel: model.family ?? root.family ?? root.display_name,
        rootCatalogId: root.id,
        rootSlug: root.slug,
        slug: model.slug,
      };
    }),
    overlay: [...overlay.entries()].map(([artifactSha256, lineage]) => ({ artifactSha256, lineage })),
  };
}

export function resolveFamily(
  input: CatalogModel | FamilyResolutionIndexModel | CommunityBoardRow,
  context: FamilyResolutionContext,
): FamilyResolution {
  if (isCommunityBoardRow(input)) return resolveCommunityFamily(input, context);
  if (isCatalogModel(input)) {
    const entry = context.catalog.find((candidate) => candidate.catalogId === input.id);
    return entry === undefined
      ? fallbackCatalogResolution(input)
      : resolutionFromCatalogEntry(entry, "lineage");
  }
  const entry = context.catalog.find((candidate) =>
    candidate.catalogId === input.catalog_id || candidate.slug === input.slug,
  );
  if (entry !== undefined) return resolutionFromCatalogEntry(entry, "lineage");
  const rootCatalogId = input.catalog_id ?? null;
  return {
    chainCatalogIds: rootCatalogId === null ? [] : [rootCatalogId],
    confidence: "lineage",
    familyLabel: input.family,
    rootCatalogId,
    rootSlug: input.slug,
  };
}

function isCommunityBoardRow(input: CatalogModel | FamilyResolutionIndexModel | CommunityBoardRow): input is CommunityBoardRow {
  return "artifactSha256" in input
    && typeof input.artifactSha256 === "string"
    && "submissionId" in input
    && typeof input.submissionId === "string";
}

function isCatalogModel(input: CatalogModel | FamilyResolutionIndexModel): input is CatalogModel {
  return "id" in input && typeof input.id === "string"
    && "display_name" in input && typeof input.display_name === "string";
}

export function familyResolutionKey(resolution: FamilyResolution): string | null {
  return resolution.rootCatalogId ?? resolution.rootSlug ?? resolution.familyLabel;
}

export function familyRootLabelBySlug(
  models: readonly FamilyResolutionIndexModel[],
  context: FamilyResolutionContext,
): ReadonlyMap<string, string> {
  const labels = new Map<string, string>();
  for (const model of models) {
    const resolution = resolveFamily(model, context);
    if (resolution.chainCatalogIds.length < 2 || resolution.rootCatalogId === null) continue;
    const root = context.catalog.find((entry) => entry.catalogId === resolution.rootCatalogId);
    if (root !== undefined) labels.set(model.slug, root.displayName);
  }
  return labels;
}

export function familyCatalogEntryForArtifactSha(
  artifactSha256: string,
  context: FamilyResolutionContext,
): FamilyResolutionCatalogEntry | undefined {
  return context.catalog.find((entry) => entry.artifactSha256s.includes(artifactSha256));
}

export function overlayLineageForArtifactSha(
  artifactSha256: string,
  context: FamilyResolutionContext,
): CommunityLineage | undefined {
  return context.overlay.find((entry) => entry.artifactSha256 === artifactSha256)?.lineage;
}

function resolveCommunityFamily(
  row: CommunityBoardRow,
  context: FamilyResolutionContext,
): FamilyResolution {
  if (row.chainCatalogIds !== undefined && row.confidence !== undefined) {
    return {
      chainCatalogIds: row.chainCatalogIds,
      confidence: row.confidence,
      familyLabel: row.familyLabel ?? null,
      rootCatalogId: row.rootCatalogId ?? null,
      rootSlug: row.rootSlug ?? null,
    };
  }

  const artifactEntry = familyCatalogEntryForArtifactSha(row.artifactSha256, context);
  if (artifactEntry !== undefined) return resolutionFromCatalogEntry(artifactEntry, "artifact-sha");

  const overlayLineage = overlayLineageForArtifactSha(row.artifactSha256, context);
  const overlayEntry = overlayLineage === undefined
    ? undefined
    : catalogEntryForRepositories(repositoriesForLineage(overlayLineage), context);
  if (overlayEntry !== undefined) return resolutionFromCatalogEntry(overlayEntry, "lineage");

  const declaredEntry = catalogEntryForRepositories(repositoriesForRow(row), context);
  if (declaredEntry !== undefined) return resolutionFromCatalogEntry(declaredEntry, "lineage");

  const declaredFamily = row.family === null ? "" : normalizedIdentity(row.family);
  if (declaredFamily !== "") {
    const familyEntry = context.catalog.find((entry) => normalizedIdentity(entry.familyLabel) === declaredFamily);
    if (familyEntry !== undefined) {
      return {
        chainCatalogIds: [],
        confidence: "declared-family",
        familyLabel: familyEntry.familyLabel,
        rootCatalogId: null,
        rootSlug: null,
      };
    }
  }

  const displayName = normalizedIdentity(row.displayName);
  const exactEntry = context.catalog.find((entry) =>
    normalizedIdentity(entry.slug) === displayName || normalizedIdentity(entry.displayName) === displayName,
  );
  return exactEntry === undefined
    ? unresolvedFamily()
    : resolutionFromCatalogEntry(exactEntry, "exact-name");
}

function resolutionFromCatalogEntry(
  entry: FamilyResolutionCatalogEntry,
  confidence: Exclude<FamilyResolutionConfidence, "declared-family" | null>,
): FamilyResolution {
  return {
    chainCatalogIds: entry.chainCatalogIds,
    confidence,
    familyLabel: entry.familyLabel,
    rootCatalogId: entry.rootCatalogId,
    rootSlug: entry.rootSlug,
  };
}

function fallbackCatalogResolution(entry: CatalogModel): FamilyResolution {
  return {
    chainCatalogIds: [entry.id],
    confidence: "lineage",
    familyLabel: entry.family ?? entry.display_name,
    rootCatalogId: entry.id,
    rootSlug: entry.slug,
  };
}

function catalogEntryForRepositories(
  repositories: readonly string[],
  context: FamilyResolutionContext,
): FamilyResolutionCatalogEntry | undefined {
  for (const repository of repositories) {
    const entry = context.catalog.find((candidate) => candidate.catalogId === repository);
    if (entry !== undefined) return entry;
  }
  return undefined;
}

function repositoriesForRow(row: CommunityBoardRow): readonly string[] {
  return [
    ...(row.lineage === undefined ? [] : repositoriesForLineage(row.lineage)),
    ...(row.declaredBaseModels ?? []),
  ];
}

function repositoriesForLineage(lineage: CommunityLineage): readonly string[] {
  return [
    lineage.repo.id,
    ...lineage.card_declared_edges.flatMap((edge) => [edge.child, edge.base]),
  ];
}

function catalogArtifactSha256s(model: CatalogModel): readonly string[] {
  const artifactSha256s: string[] = [];
  for (const quant of model.quants) {
    if (quant.file_sha256 !== null && quant.file_sha256 !== undefined) {
      artifactSha256s.push(quant.file_sha256);
    }
    for (const artifact of quant.artifact_files ?? []) artifactSha256s.push(artifact.file_sha256);
  }
  return artifactSha256s;
}

function normalizedIdentity(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "");
}

function unresolvedFamily(): FamilyResolution {
  return {
    chainCatalogIds: [],
    confidence: null,
    familyLabel: null,
    rootCatalogId: null,
    rootSlug: null,
  };
}

import type { CatalogModel } from "./schemas";

export type CatalogLineageRelation = "family-finetune" | "base-model";

export type CatalogLineageLookup = {
  readonly byId: ReadonlyMap<string, CatalogModel>;
  readonly bySlug: ReadonlyMap<string, CatalogModel>;
};

export type CatalogLineageCandidate = {
  readonly modelSlug: string;
  readonly modelLabel: string;
};

export type CatalogLineageRoot = {
  readonly key: string;
  readonly label: string;
  readonly slug: string | null;
};

export type CatalogLineageFamilyEntry = {
  readonly entry: CatalogModel;
  readonly relation: CatalogLineageRelation;
};

export function catalogModelMap(catalog: readonly CatalogModel[]): ReadonlyMap<string, CatalogModel> {
  return new Map(catalog.map((model) => [model.id, model]));
}

export function catalogLineageLookup(catalog: readonly CatalogModel[]): CatalogLineageLookup {
  return {
    byId: catalogModelMap(catalog),
    bySlug: new Map(catalog.map((model) => [model.slug, model])),
  };
}

export function catalogBaseIds(entry: CatalogModel): readonly string[] {
  if (typeof entry.base_model === "string") {
    return [entry.base_model];
  }
  return entry.base_model ?? [];
}

export function catalogBaseId(entry: CatalogModel): string | null {
  return catalogBaseIds(entry)[0] ?? null;
}

export function catalogBaseEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): CatalogModel | undefined {
  const baseId = catalogBaseId(entry);
  return baseId === null ? undefined : byId.get(baseId);
}

export function catalogIsDerivativeEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): boolean {
  return entry.model_kind !== "base" || catalogBaseEntry(entry, byId) !== undefined;
}

export function catalogRootEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): CatalogModel {
  const visited = new Set<string>([entry.id]);
  let current = entry;

  while (true) {
    const baseId = catalogBaseId(current);
    if (baseId === null) {
      return current;
    }
    const base = byId.get(baseId);
    if (base === undefined || visited.has(base.id)) {
      return current;
    }
    visited.add(base.id);
    current = base;
  }
}

export function catalogRootIdentity(entry: CatalogModel): CatalogLineageRoot {
  return { key: entry.id, label: entry.display_name, slug: entry.slug };
}

export function catalogModelRootForCandidate(
  candidate: CatalogLineageCandidate,
  lookup: CatalogLineageLookup | null,
): CatalogLineageRoot {
  const entry = lookup?.bySlug.get(candidate.modelSlug);
  return entry === undefined ? catalogCandidateFallbackRoot(candidate) : catalogRootIdentity(entry);
}

export function catalogWeightsFamilyRootForCandidate(
  candidate: CatalogLineageCandidate,
  lookup: CatalogLineageLookup | null,
): CatalogLineageRoot {
  const entry = lookup?.bySlug.get(candidate.modelSlug);
  if (entry === undefined || lookup === null) {
    return catalogCandidateFallbackRoot(candidate);
  }
  return catalogRootIdentity(catalogRootEntry(entry, lookup.byId));
}

export function catalogLineageFamilyEntries({
  byId,
  catalogEntry,
  catalogModels,
}: {
  readonly byId: ReadonlyMap<string, CatalogModel>;
  readonly catalogEntry: CatalogModel;
  readonly catalogModels: readonly CatalogModel[];
}): readonly CatalogLineageFamilyEntry[] {
  const base = catalogBaseEntry(catalogEntry, byId);
  if (base !== undefined && catalogIsDerivativeEntry(catalogEntry, byId)) {
    const root = catalogRootEntry(catalogEntry, byId);
    return root.id === catalogEntry.id ? [] : [{ entry: root, relation: "base-model" }];
  }

  return catalogModels
    .filter(
      (entry) =>
        entry.id !== catalogEntry.id &&
        catalogDescendsFrom(entry, catalogEntry.id, byId) &&
        catalogIsDerivativeEntry(entry, byId),
    )
    .map((entry) => ({ entry, relation: "family-finetune" }));
}

export function catalogDescendsFrom(
  entry: CatalogModel,
  ancestorId: string,
  byId: ReadonlyMap<string, CatalogModel>,
): boolean {
  return catalogDescendsFromInner(entry, ancestorId, byId, new Set([entry.id]));
}

function catalogDescendsFromInner(
  entry: CatalogModel,
  ancestorId: string,
  byId: ReadonlyMap<string, CatalogModel>,
  visited: Set<string>,
): boolean {
  for (const baseId of catalogBaseIds(entry)) {
    if (baseId === ancestorId) {
      return true;
    }
    const base = byId.get(baseId);
    if (base !== undefined && !visited.has(base.id)) {
      visited.add(base.id);
      if (catalogDescendsFromInner(base, ancestorId, byId, visited)) {
        return true;
      }
    }
  }
  return false;
}

function catalogCandidateFallbackRoot(candidate: CatalogLineageCandidate): CatalogLineageRoot {
  return { key: candidate.modelSlug, label: candidate.modelLabel, slug: candidate.modelSlug };
}

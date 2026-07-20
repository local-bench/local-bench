import type { CatalogModel } from "./schemas";

export type CatalogLineageRelation = "family-finetune" | "base-model";

export type CatalogLineageFamilyEntry = {
  readonly entry: CatalogModel;
  readonly relation: CatalogLineageRelation;
};

export function catalogModelMap(catalog: readonly CatalogModel[]): ReadonlyMap<string, CatalogModel> {
  return new Map(catalog.map((model) => [model.id, model]));
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
  return catalogLineageChainEntries(entry, byId).at(-1) ?? entry;
}

export function catalogLineageChainEntries(
  entry: CatalogModel,
  byId: ReadonlyMap<string, CatalogModel>,
): readonly CatalogModel[] {
  const visited = new Set<string>([entry.id]);
  const chain: CatalogModel[] = [entry];
  let current = entry;

  while (true) {
    const baseId = catalogBaseId(current);
    if (baseId === null) {
      return chain;
    }
    const base = byId.get(baseId);
    if (base === undefined || visited.has(base.id)) {
      return chain;
    }
    visited.add(base.id);
    chain.push(base);
    current = base;
  }
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

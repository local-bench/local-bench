import type { CatalogModel } from "./schemas";

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

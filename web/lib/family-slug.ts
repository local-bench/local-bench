export function familySlug(family: string): string {
  return family.toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "");
}

export function compareFamilyNames(left: string, right: string): number {
  return left.localeCompare(right, "en", { numeric: true, sensitivity: "base" });
}

export type FamilyRoute = {
  readonly family: string;
  readonly slug: string;
};

export class FamilyRouteError extends Error {
  readonly conflictingFamily: string | null;
  readonly family: string;
  readonly slug: string;

  constructor(family: string, slug: string, conflictingFamily: string | null) {
    super(
      slug === ""
        ? `Family "${family}" does not produce a route slug`
        : `Families "${conflictingFamily ?? "unknown"}" and "${family}" share route slug "${slug}"`,
    );
    this.name = "FamilyRouteError";
    this.conflictingFamily = conflictingFamily;
    this.family = family;
    this.slug = slug;
  }
}

export function familyRoutes(families: readonly string[]): readonly FamilyRoute[] {
  const familyBySlug = new Map<string, string>();
  const seenFamilies = new Set<string>();
  const routes: FamilyRoute[] = [];
  for (const family of families) {
    if (seenFamilies.has(family)) continue;
    seenFamilies.add(family);
    const slug = familySlug(family);
    if (slug === "") throw new FamilyRouteError(family, slug, null);
    const conflictingFamily = familyBySlug.get(slug);
    if (conflictingFamily !== undefined) throw new FamilyRouteError(family, slug, conflictingFamily);
    familyBySlug.set(slug, family);
    routes.push({ family, slug });
  }
  return routes;
}

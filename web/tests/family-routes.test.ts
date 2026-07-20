import { describe, expect, it } from "vitest";
import { FamilyRouteError, familyRoutes } from "../lib/family-slug";

describe("family routes", () => {
  it("rejects a family name that cannot produce a route slug", () => {
    // Given: a family name containing no route-safe characters.
    const families = ["---"];

    // When: family routes are derived.
    const deriveRoutes = () => familyRoutes(families);

    // Then: static export fails instead of colliding with the directory route.
    expect(deriveRoutes).toThrow(FamilyRouteError);
  });

  it("rejects distinct families that normalize to the same slug", () => {
    // Given: two distinct family names with the same normalized route identity.
    const families = ["Foo Bar", "Foo-Bar"];

    // When: family routes are derived.
    const deriveRoutes = () => familyRoutes(families);

    // Then: neither family is silently made unreachable.
    expect(deriveRoutes).toThrow(FamilyRouteError);
  });
});

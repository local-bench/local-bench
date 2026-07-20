import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import FamilyPage, { generateStaticParams } from "../app/families/[slug]/page";
import { getIndexData } from "../lib/data";
import { compareFamilyNames, familySlug } from "../lib/family-slug";
import { isFullIndexRow, scoreForMode } from "../lib/leaderboard-score";
import type { IndexModel } from "../lib/schemas";

describe("family detail page", () => {
  it("renders every model with measured headline rows first", async () => {
    // Given: an indexed family contains both measured and catalog-only models.
    const index = await getIndexData();
    const family = [...new Set(index.models.map((model) => model.family))].find((candidate) => {
      const models = index.models.filter((model) => model.family === candidate);
      return models.some(isFullIndexRow) && models.some((model) => !isFullIndexRow(model));
    });
    if (family === undefined) throw new Error("Expected an indexed family with measured and catalog-only models");
    const familyModels = index.models.filter((model) => model.family === family);
    const expectedOrder = expectedFamilyOrder(familyModels);

    // When: the family's static route is rendered.
    const html = renderToStaticMarkup(
      await FamilyPage({ params: Promise.resolve({ slug: familySlug(family) }) }),
    );

    // Then: every model link is present in measured-first, score-descending order.
    const linkPositions = expectedOrder.map((model) => html.indexOf(`href="/model/${model.slug}"`));
    expect(linkPositions.every((position) => position >= 0)).toBe(true);
    expect(linkPositions).toEqual([...linkPositions].sort((left, right) => left - right));
  });

  it("links the root breadcrumb to the family directory", async () => {
    // Given: a generated family route.
    const [firstParam] = await generateStaticParams();
    if (firstParam === undefined) throw new Error("Expected at least one generated family route");

    // When: the family page is rendered.
    const html = renderToStaticMarkup(await FamilyPage({ params: Promise.resolve(firstParam) }));

    // Then: the Model families breadcrumb returns to the directory.
    expect(html).toContain('href="/families">Model families</a>');
  });

  it("generates every distinct family slug exactly once", async () => {
    // Given: the distinct family slugs in the exported index.
    const index = await getIndexData();
    const expectedSlugs = [...new Set(index.models.map((model) => familySlug(model.family)))].sort();

    // When: static family parameters are generated.
    const params = await generateStaticParams();
    const actualSlugs = params.map((param) => param.slug);

    // Then: no family route is missing or duplicated.
    expect(actualSlugs).toHaveLength(new Set(actualSlugs).size);
    expect([...actualSlugs].sort()).toEqual(expectedSlugs);
  });
});

function expectedFamilyOrder(models: readonly IndexModel[]): readonly IndexModel[] {
  return [...models].sort((left, right) => {
    const leftScore = isFullIndexRow(left) ? scoreForMode(left, "full")?.point ?? null : null;
    const rightScore = isFullIndexRow(right) ? scoreForMode(right, "full")?.point ?? null : null;
    if (leftScore !== null && rightScore !== null) {
      return rightScore - leftScore || compareFamilyNames(left.model_label, right.model_label);
    }
    if (leftScore !== null) return -1;
    if (rightScore !== null) return 1;
    return compareFamilyNames(left.model_label, right.model_label);
  });
}

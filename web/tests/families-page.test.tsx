import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import FamiliesPage from "../app/families/page";
import { getIndexData } from "../lib/data";

describe("model families page", () => {
  it("renders indexed families and their model links in the directory", async () => {
    // Given: the exported index contains model-family records.
    const index = await getIndexData();
    const firstVisibleModel = [...index.models].sort(
      (left, right) => left.family.localeCompare(right.family) || left.model_label.localeCompare(right.model_label),
    )[0];
    if (firstVisibleModel === undefined) throw new Error("Expected the exported index to contain at least one model");

    // When: the dedicated families route is prerendered.
    const html = renderToStaticMarkup(await FamiliesPage());

    // Then: the directory heading, a family, and its model link are present.
    expect(html).toContain("Browse by model family");
    expect(html).toContain(firstVisibleModel.family);
    expect(html).toContain(`href="/model/${firstVisibleModel.slug}"`);
  });
});

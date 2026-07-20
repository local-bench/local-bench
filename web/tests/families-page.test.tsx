import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import FamiliesPage from "../app/families/page";
import { getIndexData } from "../lib/data";
import { familySummaries } from "../lib/families";

describe("model families page", () => {
  it("renders indexed families and their model links in the directory", async () => {
    // Given: the exported index contains model-family records.
    const index = await getIndexData();
    const firstFamily = familySummaries(index.models)[0];
    if (firstFamily === undefined) throw new Error("Expected the exported index to contain at least one family");
    const firstVisibleModel = firstFamily.models[0]?.model;
    if (firstVisibleModel === undefined) throw new Error("Expected the exported index to contain at least one model");

    // When: the dedicated families route is prerendered.
    const html = renderToStaticMarkup(await FamiliesPage());

    // Then: the directory heading, a family, and its model link are present.
    expect(html).toContain("Browse by model family");
    expect(html).toContain(firstVisibleModel.family);
    expect(html).toContain(`href="/families/${firstFamily.slug}/"`);
    expect(html).toContain(`href="/model/${firstVisibleModel.slug}/"`);
  });
});

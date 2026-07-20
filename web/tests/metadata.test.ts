import { describe, expect, it } from "vitest";
import { metadata as leaderboardMetadata } from "../app/leaderboard/page";
import {
  generateMetadata as generateFamilyMetadata,
  generateStaticParams as generateFamilyStaticParams,
} from "../app/families/[slug]/page";
import {
  generateMetadata as generateModelMetadata,
  generateStaticParams as generateModelStaticParams,
} from "../app/model/[slug]/page";
import { getModelPageData } from "../lib/data";

describe("page metadata titles", () => {
  it("keeps model, family, and leaderboard routes uniquely titled", async () => {
    // Given: one statically generated model route and one family route.
    const [modelParam] = await generateModelStaticParams();
    const [familyParam] = await generateFamilyStaticParams();
    if (modelParam === undefined || familyParam === undefined) {
      throw new Error("Expected generated model and family routes");
    }
    const model = (await getModelPageData(modelParam.slug)).model;

    // When: their metadata objects are generated directly.
    const [modelMetadata, familyMetadata] = await Promise.all([
      generateModelMetadata({ params: Promise.resolve(modelParam) }),
      generateFamilyMetadata({ params: Promise.resolve(familyParam) }),
    ]);

    // Then: each route owns a descriptive title instead of inheriting the site default.
    expect(modelMetadata.title).toBe(`${model.model_label} — local benchmark scores, quants, VRAM`);
    expect(familyMetadata.title).toContain("models and benchmarks");
    expect(leaderboardMetadata.title).toBe("Local LLM leaderboard");
    expect(new Set([modelMetadata.title, familyMetadata.title, leaderboardMetadata.title]).size).toBe(3);
  });
});

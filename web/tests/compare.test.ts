import { describe, expect, it } from "vitest";
import { getCompareConfigs } from "../lib/compare";
import { getIndexData, getModelData } from "../lib/data";

describe("compare configs", () => {
  it("includes measured configs with nonstandard quant labels and labels index coverage", async () => {
    // Given measured site data that includes a project-anchor Unsloth dynamic quant.
    const index = await getIndexData();
    const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));

    // When compare configs are built from measured runs.
    const configs = getCompareConfigs(models);

    // Then the nonstandard QAT Q4_K_XL measured variant is available and marked rank-comparable.
    expect(
      configs.find((config) => config.modelSlug === "gemma-4-12b-it" && config.quantLabel === "QAT Q4_K_XL"),
    ).toMatchObject({
      coverage: "full",
      modelSlug: "gemma-4-12b-it",
      quantLabel: "QAT Q4_K_XL",
    });
    expect(configs.find((config) => config.modelSlug === "gemma-4-12b-it" && config.quantLabel === "Q8_0")).toMatchObject({
      coverage: "partial",
      modelSlug: "gemma-4-12b-it",
      quantLabel: "Q8_0",
    });
  });
});

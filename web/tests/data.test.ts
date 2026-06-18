import { describe, expect, it } from "vitest";
import {
  getIndexData,
  getModelPageData,
  getModelStaticParams,
  getRunStaticParams,
} from "../lib/data";

describe("static data access", () => {
  it("loads every catalog model as a score-less shell in the index", async () => {
    // Given an empty benchmark source list and the checked-in model catalog.
    // When the generated index is loaded.
    const index = await getIndexData();
    const qwen = index.models.find((model) => model.slug === "qwen3-0-6b");

    // Then the catalog is browsable without invented benchmark scores.
    expect(index.models).toHaveLength(102);
    expect(qwen).toMatchObject({
      best_run_id: null,
      composite: null,
      model_label: "Qwen3 0.6B",
      n_runs: 0,
      score_status: "missing",
    });
  });

  it("loads a catalog model page with quant shells and no run-detail params", async () => {
    // Given a model that exists only in the catalog.
    // When the model page data and static route params are assembled.
    const pageData = await getModelPageData("qwen3-0-6b");
    const modelParams = await getModelStaticParams();
    const runParams = await getRunStaticParams();

    // Then the model page has data-ready quant shells, but no fake run receipts.
    expect(modelParams).toContainEqual({ slug: "qwen3-0-6b" });
    expect(runParams).toHaveLength(0);
    expect(pageData.model.model_label).toBe("Qwen3 0.6B");
    expect(pageData.model.runs.map((run) => [run.quant_label, run.file_gb, run.vram_required_gb_8k, run.run_id, run.composite])).toEqual([
      ["Q8_0", 0.6, 1.7, null, null],
      ["Q6_K", 0.5, 1.5, null, null],
      ["Q5_K_M", 0.4, 1.5, null, null],
      ["Q4_K_M", 0.4, 1.4, null, null],
      ["Q3_K_M", 0.3, 1.3, null, null],
      ["Q2_K", 0.2, 1.3, null, null],
    ]);
  });
});

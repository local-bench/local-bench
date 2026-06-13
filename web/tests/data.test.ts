import { describe, expect, it } from "vitest";
import {
  AXES,
  getIndexData,
  getModelPageData,
  getModelStaticParams,
  getRunData,
  getRunStaticParams,
} from "../lib/data";

describe("static data access", () => {
  it("loads ranked home rows when generated index JSON exists", async () => {
    // Given the generated suite-v0 index file.
    // When the home data is loaded.
    const index = await getIndexData();

    // Then every model row has a best run and the default order is composite descending.
    expect(index.suite_version).toBe("suite-v0");
    expect(index.models.length).toBeGreaterThan(0);
    expect(index.models.every((model) => model.best_run_id.length > 0)).toBe(true);
    expect(index.models.map((model) => model.composite.point)).toEqual(
      [...index.models]
        .sort((left, right) => right.composite.point - left.composite.point)
        .map((model) => model.composite.point),
    );
  });

  it("loads a model page with its runs plus global anchor references", async () => {
    // Given a community model page.
    // When the model page data is assembled.
    const index = await getIndexData();
    const pageData = await getModelPageData("qwen3-5-9b");
    const anchorCount = index.models.filter((model) => model.kind === "anchor").length;

    // Then local runs stay with the model and frontier anchors are available as reference lines.
    expect(pageData.model.model_label).toBe("Qwen3.5 9B");
    expect(pageData.model.runs.length).toBe(3);
    expect(pageData.anchorRuns.length).toBe(anchorCount);
    expect(pageData.model.runs.every((run) => run.vram_footprint_gb === null)).toBe(true);
  });

  it("plumbs demo flags through generated model and run data", async () => {
    // Given generated data that includes the Phase-3 synthetic preview set.
    // When the demo model and an existing real local model are loaded.
    const index = await getIndexData();
    const demoModel = await getModelPageData("qwen3-32b");
    const realModel = await getModelPageData("qwen3-5-9b");
    const demoRun = await getRunData("qwen3-32b__demo-qwen3-32b-q4-k-m");
    const realIndexRow = index.models.find((model) => model.model_label === "Qwen3.5 9B");

    // Then only the synthetic preview records carry demo=true; real records default to demo=false.
    expect(index.models.filter((model) => model.demo).map((model) => model.model_label)).toContain("Qwen3 32B");
    expect(demoModel.model.runs.map((run) => run.demo)).toEqual([true, true, true, true, true]);
    expect(demoRun.demo).toBe(true);
    expect(realIndexRow?.demo).toBe(false);
    expect(realModel.model.runs.every((run) => run.demo === false)).toBe(true);
  });

  it("loads huge synthetic demo ladders without changing the real Qwen triplet", async () => {
    // Given generated data that includes Phase-3 huge model demo ladders.
    const index = await getIndexData();

    // When the huge demo model pages and the real Qwen model page are loaded.
    const llama405b = await getModelPageData("llama-3-1-405b");
    const deepseekV3 = await getModelPageData("deepseek-v3-671b");
    const realModel = await getModelPageData("qwen3-5-9b");

    // Then the demo ladders are complete, large-tier compatible, and real run data stays unchanged.
    expect(index.models.filter((model) => model.demo).map((model) => model.model_label)).toEqual(
      expect.arrayContaining(["Llama-3.1-405B", "DeepSeek-V3-671B"]),
    );
    expect(llama405b.model.runs.map((run) => [run.quant_label, run.vram_footprint_gb, run.composite.point, run.tok_s])).toEqual([
      ["FP16", 810, 82, 5],
      ["Q8_0", 405, 81, 7],
      ["Q5_K_M", 290, 79.5, 10],
      ["Q4_K_M", 230, 78, 12],
      ["Q3_K_M", 180, 75, 15],
    ]);
    expect(deepseekV3.model.runs.map((run) => [run.quant_label, run.vram_footprint_gb, run.composite.point, run.tok_s])).toEqual([
      ["FP16", 1340, 84, 8],
      ["Q8_0", 670, 83, 10],
      ["Q5_K_M", 470, 81.5, 14],
      ["Q4_K_M", 380, 80, 17],
      ["Q3_K_M", 300, 77, 20],
    ]);
    expect(realModel.model.runs).toHaveLength(3);
    expect(realModel.model.runs.every((run) => run.vram_footprint_gb === null && run.demo === false)).toBe(true);
  });

  it("loads run detail axes in the published order", async () => {
    // Given a known run detail file.
    // When the detail data is loaded.
    const run = await getRunData("qwen3-5-9b__quick-9b-var1");

    // Then all three axes are present and the worst-axis field points to one of them.
    expect(AXES.map((axis) => run.axes[axis].point)).toHaveLength(3);
    expect(AXES).toContain(run.worst_axis.bench);
    expect(run.composite.point).toBeGreaterThan(0);
  });

  it("derives static params from the generated index and model files", async () => {
    // Given generated index and per-model data files.
    // When static params are derived for app-router pages.
    const modelParams = await getModelStaticParams();
    const runParams = await getRunStaticParams();

    // Then both dynamic route sets include the published community and anchor data.
    expect(modelParams).toContainEqual({ slug: "qwen3-5-9b" });
    expect(runParams).toContainEqual({ runId: "qwen3-5-9b__quick-9b-var1" });
    expect(runParams).toContainEqual({ runId: "gpt-5-5__anchor-gpt55-quick" });
  });
});

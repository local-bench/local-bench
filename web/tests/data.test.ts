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

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelVariantBoard } from "../components/model-variant-board";
import { AXIS_CONFIG, axisLabel } from "../lib/axis-config";
import { getModelData } from "../lib/data";
import { formatScore } from "../lib/format";

describe("tool-calling presentation", () => {
  it("treats tool_calling as a canonical displayed axis", () => {
    // Given: tc_json_v1 run results are projected as the site axis key tool_calling.
    const axisKeys = AXIS_CONFIG.map((axis) => axis.key);

    // Then: the axis has a stable display label and order rather than falling through.
    expect(axisKeys).toEqual(["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"]);
    expect(axisLabel("tool_calling")).toBe("Tool calling");
  });

  it("renders measured tool-calling results on the model variant board", async () => {
    // Given: a model with completed tc_json_v1 results in the generated public data.
    const model = await getModelData("qwen3-6-35b-a3b");
    const q4Run = model.runs.find((run) => run.quant_label === "Q4_K_M");
    const toolCalling = q4Run?.axes.tool_calling;
    if (toolCalling === undefined) {
      expect.fail("expected Qwen3.6 35B A3B Q4_K_M to have a measured tool_calling axis");
    }

    // When: the model variant table is rendered.
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));

    // Then: the visible table uses the user-facing Tool calling label and measured score.
    expect(html).toContain("Tool calling");
    expect(html).toContain(formatScore(toolCalling.point));
    expect(html).not.toContain("JSON gate");
  });
});

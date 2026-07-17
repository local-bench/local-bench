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

  it("renders measured season-2 tool-use results on the model variant board", async () => {
    // Given: a model with completed season-2 tool-use facets on the current lane.
    const model = await getModelData("gemma-4-12b-it");
    const currentRun = model.runs.find((run) => run.lane === "bounded-final-v2");
    const toolUse = currentRun?.axes["tool_use"];
    if (toolUse === undefined) {
      expect.fail("expected Gemma 4 12B's season-2 run to have a measured tool_use axis");
    }

    // When: the model variant table is rendered.
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));

    // Then: the visible table uses the season-2 macro-axis label (Agentic, key tool_use)
    // and the measured score.
    expect(html).toContain("Agentic");
    expect(html).toContain(formatScore(toolUse.point));
    expect(html).not.toContain("JSON gate");
  });
});

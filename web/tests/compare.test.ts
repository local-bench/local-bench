import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComparePicker } from "../components/compare-picker";
import { getCompareConfigs } from "../lib/compare";
import { getIndexData, getModelData } from "../lib/data";
import { HEADLINE_LANE } from "../lib/leaderboard-score";

const CURRENT_RUN_ID = "gemma-4-12b-it__gemma-4-12b-it-qat-ud-q4kxl-bounded-final-v2";
const LEGACY_RUN_ID = "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q4";

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

  it("defaults to current-lane configs and quarantines legacy runs behind diagnostics", async () => {
    // Given measured site data with one current ranked run and previous-index diagnostics.
    const configs = await realCompareConfigs();

    // When the picker renders without URL-selected run ids.
    const html = renderToStaticMarkup(
      createElement(ComparePicker, {
        configs,
        fineTunePresets: [],
        initialLeftId: null,
        initialRightId: null,
      }),
    );

    // Then selected cards are current-index only, while retired runs are opt-in diagnostics.
    expect(configs.some((config) => config.runId === LEGACY_RUN_ID)).toBe(true);
    expect(html).toContain(CURRENT_RUN_ID);
    expect(html).toContain(`value="${LEGACY_RUN_ID}"`);
    expect(html).toContain("Previous-index diagnostics");
    expect(html).not.toContain("62.3");
    expect(html).not.toContain("62.0");
  });

  it("does not render an Index delta when a URL-selected side is a legacy run", async () => {
    // Given a legacy run id selected through the same prop path used for URL ids.
    const configs = await realCompareConfigs();

    // When the compare picker renders that diagnostic side.
    const html = renderToStaticMarkup(
      createElement(ComparePicker, {
        configs,
        fineTunePresets: [],
        initialLeftId: LEGACY_RUN_ID,
        initialRightId: CURRENT_RUN_ID,
      }),
    );

    // Then the retired composite is framed diagnostically and no current Index delta is shown.
    expect(html).toContain("Diagnostic score (retired lane)");
    expect(html).toContain(HEADLINE_LANE);
    expect(html).not.toContain("Local Intelligence Index delta");
  });
});

async function realCompareConfigs() {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  return getCompareConfigs(models);
}

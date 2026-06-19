import { readModelData } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

const MODEL_CASES = [
  { slug: "gemma-3-27b", screenshotName: "model-gemma-3-27b" },
  { slug: "qwen3-6-27b", screenshotName: "model-qwen3-6-27b" },
  { slug: "qwen3-32b", screenshotName: "model-qwen3-32b" },
] as const;

for (const modelCase of MODEL_CASES) {
  test(`renders model page for ${modelCase.slug} with matrix, scatter, and run links`, async ({ page }) => {
    const model = await readModelData(modelCase.slug);

    await visitRoute(page, `/model/${modelCase.slug}/`);

    await expect(page.getByRole("heading", { name: model.model_label })).toBeVisible();
    await expect(page.getByTestId("quant-decision-matrix")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Decision matrix" })).toBeVisible();
    await expect(
      page.getByRole("img", { name: new RegExp(`${escapeRegExp(model.model_label)} Local Intelligence Index`) }),
    ).toBeVisible();
    await expect(page.getByTestId("model-axis-profile")).toBeVisible();

    const runLinks = page.getByTestId("model-runs-table").locator('tbody a[href^="/run/"]');
    await expect(runLinks).toHaveCount(model.runs.length);
    for (const run of model.runs) {
      await expect(page.getByTestId("model-runs-table").getByRole("link", { name: run.run_id })).toHaveAttribute(
        "href",
        new RegExp(`^/run/${escapeRegExp(run.run_id)}/?$`),
      );
    }

    if (modelCase.slug === "qwen3-6-27b") {
      await expect(page.getByText(/FP16 baseline missing/i)).toBeVisible();
      await expect(page.getByTestId("quant-decision-matrix").getByRole("row", { name: /Q8_0.*Baseline/ })).toBeVisible();
      await expect(page.getByTestId("quant-decision-matrix").getByRole("row", { name: /Q3_K_M.*Sweet spot/ })).toBeVisible();
      await expect(page.getByTestId("quant-decision-matrix").getByRole("row", { name: /Q2_K.*-6\.6/ })).toBeVisible();
    }
    if (modelCase.slug === "qwen3-32b") {
      await expect(page.getByTestId("quant-decision-matrix").getByText("Sweet spot")).toBeVisible();
      await expect(page.getByTestId("quant-decision-matrix").getByRole("row", { name: /Q5_K_M.*Sweet spot/ })).toBeVisible();
    }

    await capturePage(page, modelCase.screenshotName);
  });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

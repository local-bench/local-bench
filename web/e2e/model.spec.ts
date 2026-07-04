import { readModelData } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

const MODEL_CASES = [
  { slug: "gemma-3-27b-it", screenshotName: "model-gemma-3-27b-it" },
  { slug: "qwen3-6-27b", screenshotName: "model-qwen3-6-27b" },
  { slug: "qwen3-32b", screenshotName: "model-qwen3-32b" },
] as const;

for (const modelCase of MODEL_CASES) {
  test(`renders model page for ${modelCase.slug} with ranked variant board, scatter, and run links`, async ({ page }) => {
    const model = await readModelData(modelCase.slug);

    await visitRoute(page, `/model/${modelCase.slug}/`);

    await expect(page.getByRole("heading", { name: model.model_label })).toBeVisible();
    await expect(page.getByTestId("model-variant-board")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Variants ranked" })).toBeVisible();
    await expect(
      page.getByRole("img", { name: new RegExp(`${escapeRegExp(model.model_label)} Local Intelligence Index`) }),
    ).toBeVisible();

    // Every measured run (one with a run_id) gets a receipt link to its /run/ page in the board.
    const measuredRunIds = model.runs.map((run) => run.run_id).filter((id): id is string => id !== null);
    const receiptLinks = page.getByTestId("model-variant-table").locator('a[href^="/run/"]');
    await expect(receiptLinks).toHaveCount(measuredRunIds.length);
    for (const runId of measuredRunIds) {
      await expect(page.getByTestId("model-variant-table").locator(`a[href^="/run/${runId}"]`)).toHaveCount(1);
    }

    if (modelCase.slug === "qwen3-6-27b") {
      // Quants are differentiated (not flat) and ranked descending: the best variant (Q6_K) is row 1
      // with the "best" badge, and Q2_K — the degraded rung — sorts last.
      const rows = page.getByTestId("model-variant-table").locator("tbody tr");
      await expect(rows.first()).toContainText("Q6_K");
      await expect(rows.first()).toContainText("best");
    }

    await capturePage(page, modelCase.screenshotName);
  });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

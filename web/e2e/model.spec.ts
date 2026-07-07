import { readModelData, runIds } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

const HEADLINE_LANE = "bounded-final-v2";

const MODEL_CASES = [
  { slug: "gemma-3-27b-it", screenshotName: "model-gemma-3-27b-it" },
  { slug: "qwen3-6-27b", screenshotName: "model-qwen3-6-27b" },
  { slug: "qwen3-32b", screenshotName: "model-qwen3-32b" },
  { slug: "gemma-4-12b-it", screenshotName: "model-gemma-4-12b-it" },
] as const;

for (const modelCase of MODEL_CASES) {
  test(`renders model page for ${modelCase.slug} with lane-scoped variant board and run links`, async ({ page }) => {
    const model = await readModelData(modelCase.slug);
    const measured = model.runs.filter((run) => run.score_status === "measured");
    const currentRuns = measured.filter((run) => run.lane === HEADLINE_LANE);
    const legacyRuns = measured.filter((run) => run.lane !== HEADLINE_LANE);

    await visitRoute(page, `/model/${modelCase.slug}/`);

    await expect(page.getByRole("heading", { name: model.model_label, exact: true })).toBeVisible();
    await expect(page.getByTestId("model-variant-board")).toBeVisible();

    const currentRunIds = runIds(currentRuns);
    const legacyRunIds = runIds(legacyRuns);
    const boardReceipts = page.getByTestId("model-variant-table").locator('a[href^="/run/"]');
    await expect(boardReceipts).toHaveCount(currentRunIds.length);
    for (const runId of currentRunIds) {
      await expect(page.getByTestId("model-variant-table").locator(`a[href^="/run/${runId}"]`)).toHaveCount(1);
    }

    await expect(page.getByTestId("model-legacy-diagnostics")).toHaveCount(0);
    for (const runId of legacyRunIds) {
      await expect(page.getByTestId("model-variant-table").locator(`a[href^="/run/${runId}"]`)).toHaveCount(0);
    }

    if (legacyRunIds.length === 0) {
      await expect(page.getByText("Retired-lane diagnostic receipts", { exact: true })).toHaveCount(0);
    } else {
      await expect(page.getByText("Retired-lane diagnostic receipts", { exact: true })).toBeVisible();
      for (const runId of legacyRunIds) {
        const receipt = page.locator(`a[href*="${runId}"]`);
        await expect(receipt).toHaveCount(1);
        await expect(receipt).toContainText("diagnostic receipt (retired lane)");
      }
    }

    if (modelCase.slug === "qwen3-6-27b") {
      // A legacy-only model: no rank or "best" badge in the variant board (its catalog shells
      // stay pending with benchmark CTAs), and the measured quant ladder survives as diagnostics.
      await expect(page.getByTestId("model-variant-table")).not.toContainText("best");
      await expect(page.getByTestId("model-variant-table")).toContainText("benchmark it");
      await expect(page.locator("header div").filter({ hasText: "Retired-lane diagnostic receipts" }).first()).toContainText(
        "Q6_K",
      );
    }

    if (modelCase.slug === "gemma-4-12b-it") {
      // The ranked bounded-final row is the only row with a rank and the "best" badge.
      const rows = page.getByTestId("model-variant-table").locator("tbody tr");
      await expect(rows.first()).toContainText("QAT Q4_K_XL");
      await expect(rows.first()).toContainText("best");
      await expect(
        page.getByRole("img", { name: new RegExp(`${escapeRegExp(model.model_label)} Local Intelligence Index`) }),
      ).toBeVisible();
    }

    await capturePage(page, modelCase.screenshotName);
  });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

import { readModelData } from "./data";
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

    await expect(page.getByRole("heading", { name: model.model_label })).toBeVisible();
    await expect(page.getByTestId("model-variant-board")).toBeVisible();

    // Current-index runs get receipt links in the variant board; legacy-lane runs are
    // omitted from the model page entirely (owner call 2026-07-07 — receipts stay
    // reachable by direct URL only).
    const currentRunIds = currentRuns.map((run) => run.run_id).filter((id): id is string => id !== null);
    const boardReceipts = page.getByTestId("model-variant-table").locator('a[href^="/run/"]');
    await expect(boardReceipts).toHaveCount(currentRunIds.length);
    for (const runId of currentRunIds) {
      await expect(page.getByTestId("model-variant-table").locator(`a[href^="/run/${runId}"]`)).toHaveCount(1);
    }

    await expect(page.getByTestId("model-legacy-diagnostics")).toHaveCount(0);
    for (const runId of legacyRuns.map((run) => run.run_id).filter((id): id is string => id !== null)) {
      await expect(page.locator(`a[href^="/run/${runId}"]`)).toHaveCount(0);
    }

    if (modelCase.slug === "qwen3-6-27b") {
      // A legacy-only model: no rank or "best" badge in the variant board (its catalog shells
      // stay pending with benchmark CTAs), and the measured quant ladder survives as diagnostics.
      await expect(page.getByTestId("model-variant-table")).not.toContainText("best");
      await expect(page.getByTestId("model-variant-table")).toContainText("benchmark it");
      await expect(page.getByTestId("model-legacy-table")).toContainText("Q6_K");
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

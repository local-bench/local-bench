import { familyReceiptRunIds, isTrustedRankedPopulation, readModelData, runIds } from "./data";
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
    // Since f54ea9d ("isolate protected populations") the variant board renders a measured
    // run only when it is headline-lane AND in the trusted ranked population
    // (web/lib/trusted-population.ts; filter in components/model-variant-board.tsx). Every
    // other measured run — retired lanes, untrusted re-scored ladder runs, and unranked
    // headline runs — is quarantined off the model page; its receipt stays reachable by
    // direct /run URL only.
    const displayedRuns = measured.filter(
      (run) => run.lane === HEADLINE_LANE && isTrustedRankedPopulation(run) && run.composite !== null,
    );
    const quarantinedRuns = measured.filter((run) => !displayedRuns.includes(run));
    // Lineage-family rows (base model / family fine-tunes, 467b9e8) render their own
    // receipt links in the same variant table.
    const familyRunIds = await familyReceiptRunIds(modelCase.slug);

    await visitRoute(page, `/model/${modelCase.slug}/`);

    const pageTitle = page.getByRole("heading", { level: 1 });
    await expect(pageTitle).toBeVisible();
    await expect(pageTitle).toContainText(model.model_label); // h1 embeds the org logo img, so exact-name matching is wrong since 3a1589c
    await expect(page.getByTestId("model-variant-board")).toBeVisible();

    const displayedRunIds = runIds(displayedRuns);
    const quarantinedRunIds = runIds(quarantinedRuns);
    const boardReceipts = page.getByTestId("model-variant-table").locator('a[href^="/run/"]');
    await expect(boardReceipts).toHaveCount(displayedRunIds.length + familyRunIds.length);
    for (const runId of [...displayedRunIds, ...familyRunIds]) {
      await expect(page.getByTestId("model-variant-table").locator(`a[href^="/run/${runId}"]`)).toHaveCount(1);
    }

    await expect(page.getByTestId("model-legacy-diagnostics")).toHaveCount(0);

    // Quarantined runs are invisible on model pages: no receipts box, no links anywhere.
    await expect(page.getByText("Retired-lane diagnostic receipts", { exact: true })).toHaveCount(0);
    for (const runId of quarantinedRunIds) {
      await expect(page.locator(`a[href*="${runId}"]`)).toHaveCount(0);
    }

    if (modelCase.slug === "qwen3-6-27b") {
      // Ranked on the current board since the SEASON-2 cutover (68aa2fb; re-scored to
      // index-v4.1 in 157bd1a): its bounded-final-v2 run carries the "best" badge, while
      // the still-unbenchmarked catalog shells keep their pending benchmark CTA. Its
      // retired-lane ladder runs stay off the page (covered by the quarantine loop above).
      await expect(page.getByTestId("model-variant-table")).toContainText("best");
      await expect(page.getByTestId("model-variant-table")).toContainText("benchmark it");
    }

    if (modelCase.slug === "gemma-4-12b-it") {
      // The ranked bounded-final row is the only row with a rank and the "best" badge.
      const rows = page.getByTestId("model-variant-table").locator("tbody tr");
      await expect(rows.first()).toContainText("QAT Q4_K_XL");
      await expect(rows.first()).toContainText("best");
      await expect(
        page.getByRole("group", { name: new RegExp(`${escapeRegExp(model.model_label)} Local Intelligence Index`) }),
      ).toBeVisible();
    }

    await capturePage(page, modelCase.screenshotName);
  });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

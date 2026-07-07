import { rankedCurrentModels, readIndexData, retiredDiagnosticModels } from "./data";
import { expect, test, visitRoute } from "./fixtures";

test("renders exactly the current-lane ranked rows and quarantines retired diagnostics", async ({ page }) => {
  const index = await readIndexData();
  const rankedRows = rankedCurrentModels(index.models);
  const retiredRows = retiredDiagnosticModels(index.models);
  test.setTimeout(Math.max(30_000, index.models.length * 500));

  await visitRoute(page, "/leaderboard");

  await expect(page.getByRole("heading", { name: "Ranked board" })).toBeVisible();
  const leaderboard = page.getByTestId("full-leaderboard");
  await expect(leaderboard).toBeVisible();
  await expect(leaderboard.locator("tbody tr")).toHaveCount(rankedRows.length);
  await expect(leaderboard.getByRole("button", { name: "Time/answer" })).toBeVisible();
  await expect(page.getByText(/Ranked rows are complete current-index runs under the bounded-final lane/i)).toBeVisible();

  for (const row of rankedRows) {
    const modelRow = leaderboard.locator("tbody tr").filter({ hasText: row.model_label });
    await expect(modelRow).toHaveCount(1);
    await expect(modelRow).toContainText(row.composite?.point.toFixed(1) ?? "");
  }

  const diagnostics = page.getByTestId("measured-diagnostics");
  await expect(diagnostics.locator("tbody tr")).toHaveCount(retiredRows.length);
  for (const row of retiredRows) {
    await expect(leaderboard.getByRole("link", { name: row.model_label, exact: true })).toHaveCount(0);
    await expect(diagnostics.getByRole("link", { name: row.model_label, exact: true })).toBeVisible();
    await expect(diagnostics.locator("tbody tr").filter({ hasText: row.model_label })).toContainText(row.lane ?? "n/a");
  }
});

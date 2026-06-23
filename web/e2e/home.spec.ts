import { expect, test, visitRoute } from "./fixtures";

test("leads with the graph + summary board, on-ramp below", async ({ page }) => {
  await visitRoute(page, "/");

  await expect(page.getByTestId("best-variant-scatter")).toBeVisible();
  await expect(page.getByTestId("best-variant-table")).toBeVisible();
  await expect(page.getByTestId("benchmark-onramp")).toBeVisible();
  await expect(page.getByTestId("full-leaderboard")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /View full leaderboard/i })).toBeVisible();

  const scatterBox = await page.getByTestId("best-variant-scatter").boundingBox();
  const onrampBox = await page.getByTestId("benchmark-onramp").boundingBox();
  expect(scatterBox).not.toBeNull();
  expect(onrampBox).not.toBeNull();
  expect(onrampBox?.y ?? 0).toBeGreaterThan(scatterBox?.y ?? 0);
});

test("the on-ramp emits a board-comparable recipe", async ({ page }) => {
  await visitRoute(page, "/");

  // A recommended model is preselected at the default VRAM tier, so a recipe renders immediately.
  await expect(page.getByTestId("benchmark-recipe")).toBeVisible();
  await expect(page.getByText(/localbench run/)).toBeVisible();
  await expect(page.getByText(/--lane capped-thinking/)).toBeVisible();
});

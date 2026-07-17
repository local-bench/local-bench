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
  // Since de1a3f3 the recipe leads with the catalog-pinned one-command flow ("localbench bench
  // ... --static-only") and 6ca5f51 relabelled the scope line to the public static path; the
  // classic board-lane `localbench run` recipe moved behind the closed "Advanced: bring your
  // own server" disclosure and is hidden until expanded.
  await expect(page.getByTestId("benchmark-recipe")).toBeVisible();
  await expect(page.getByText(/localbench bench .* --static-only/)).toBeVisible();
  await expect(page.getByText(/Public path · measured\/static · suite-v1-static-exec-5axis-v1/i)).toBeVisible();
  await expect(page.getByText(/localbench run/)).toBeHidden();

  await page.getByText(/Advanced: bring your own server/).click();

  await expect(page.getByText(/localbench run/)).toBeVisible();
  await expect(page.getByText(/--lane bounded-final-v2/)).toBeVisible();
  await expect(page.getByText(/--profile auto/)).toBeVisible();
});

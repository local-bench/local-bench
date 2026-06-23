import { expect, test, visitRoute } from "./fixtures";

test("leads with the graph + summary board, finder below", async ({ page }) => {
  await visitRoute(page, "/");

  await expect(page.getByTestId("best-variant-scatter")).toBeVisible();
  await expect(page.getByTestId("best-variant-table")).toBeVisible();
  await expect(page.getByTestId("rig-match-finder")).toBeVisible();
  await expect(page.getByTestId("full-leaderboard")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /View full leaderboard/i })).toBeVisible();

  const scatterBox = await page.getByTestId("best-variant-scatter").boundingBox();
  const finderBox = await page.getByTestId("rig-match-finder").boundingBox();
  expect(scatterBox).not.toBeNull();
  expect(finderBox).not.toBeNull();
  expect(finderBox?.y ?? 0).toBeGreaterThan(scatterBox?.y ?? 0);
});

test("supports large VRAM tiers in the finder", async ({ page }) => {
  await visitRoute(page, "/");

  const vramSelect = page.getByLabel("VRAM tier");
  await expect(vramSelect.getByRole("option", { name: "512 GB" })).toBeAttached();

  await vramSelect.selectOption("192");
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /Llama-3\.1-405B.*Q3_K_M/ })).toHaveCount(0);

  await vramSelect.selectOption("256");
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /Llama-3\.1-405B.*Q3_K_M/ })).toBeVisible();

  await vramSelect.selectOption("384");
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /DeepSeek-V3-671B.*Q4_K_M/ })).toHaveCount(0);

  await vramSelect.selectOption("512");
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /DeepSeek-V3-671B.*Q5_K_M/ })).toBeVisible();
});


import { capturePage, expect, test, visitRoute } from "./fixtures";

test("methodology explains scoring uncertainty and links back home", async ({ page }) => {
  await visitRoute(page, "/methodology");

  await expect(page.getByRole("heading", { name: "How local-bench scores runs" })).toBeVisible();
  await expect(page.getByText(/bootstrap CIs make uncertainty visible/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Absolute chance-corrected normalization" })).toBeVisible();
  await capturePage(page, "content-methodology");

  await page.getByRole("link", { name: "Back to leaderboard" }).click();
  await expect(page.getByRole("heading", { name: "Local AI quality leaderboard" })).toBeVisible();
});

test("trust page explains replication and community reporting and links back home", async ({ page }) => {
  await visitRoute(page, "/trust");

  await expect(page.getByRole("heading", { name: "Honesty is the credibility signal" })).toBeVisible();
  await expect(page.getByText(/trust unit is replication/i)).toBeVisible();
  await expect(page.getByText(/Community-reported runs/i)).toBeVisible();
  await capturePage(page, "content-trust");

  await page.getByRole("link", { name: "Back to leaderboard" }).click();
  await expect(page.getByRole("heading", { name: "Local AI quality leaderboard" })).toBeVisible();
});

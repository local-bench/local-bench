import { capturePage, expect, test, visitRoute } from "./fixtures";

test("methodology explains scoring uncertainty and links back home", async ({ page }) => {
  await visitRoute(page, "/methodology");

  await expect(page.getByRole("heading", { name: "How local-bench scores runs" })).toBeVisible();
  await expect(page.getByText(/every displayed score carries a bootstrap confidence interval/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "What the headline Index is" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Frozen as of/i })).toBeVisible();
  await capturePage(page, "content-methodology");

  await page.getByRole("link", { name: "Back to leaderboard" }).click();
  await expect(page.getByRole("heading", { name: "Local Intelligence Index" })).toBeVisible();
});

test("methodology carries the benchmark sources and licenses section", async ({ page }) => {
  await visitRoute(page, "/methodology");

  await expect(page.getByRole("heading", { name: "Benchmark sources & licenses" })).toBeVisible();
  await expect(page.getByText("MMLU-Pro")).toBeVisible();
  await expect(page.getByText(/ODC-BY-1.0/)).toBeVisible();
  await capturePage(page, "content-licenses");
});

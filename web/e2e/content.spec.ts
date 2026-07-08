import { capturePage, expect, test, visitRoute } from "./fixtures";

test("methodology explains scoring uncertainty and links back home", async ({ page }) => {
  await visitRoute(page, "/methodology");

  await expect(page.getByRole("heading", { name: "How local-bench scores runs" })).toBeVisible();
  await expect(page.getByText(/every displayed score carries a bootstrap confidence interval/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "What index-v3.0 measures" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lane and ranking rules" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Frozen as of/i })).toBeVisible();
  await capturePage(page, "content-methodology");

  await page.getByRole("link", { name: "Leaderboard" }).click();
  await expect(page.getByTestId("best-variant-scatter")).toBeVisible();
});

test("methodology carries the benchmark sources and licenses section", async ({ page }) => {
  await visitRoute(page, "/methodology");

  const licenses = page.locator("section#licenses");
  await expect(licenses.getByRole("heading", { name: "Benchmark sources & licenses" })).toBeVisible();
  await expect(licenses.getByText("MMLU-Pro", { exact: true })).toBeVisible();
  await expect(licenses.getByText(/ODC-BY-1.0/)).toBeVisible();
  await capturePage(page, "content-licenses");
});

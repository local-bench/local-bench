import { expect, test, visitRoute } from "./fixtures";

test("compares two model quant configs with deltas and axis winners", async ({ page }) => {
  // Given the compare route is the head-to-head workflow.
  // When the route is opened.
  await visitRoute(page, "/compare");

  // Then the page exposes config pickers, aggregate deltas, per-axis winners, and model links.
  await expect(page.getByRole("heading", { name: "Compare model configs" })).toBeVisible();
  await expect(page.getByLabel("Left config")).toBeVisible();
  await expect(page.getByLabel("Right config")).toBeVisible();

  await page.getByLabel("Left config").selectOption("qwen3-6-27b__lcpp-q8_0");
  await page.getByLabel("Right config").selectOption("qwen3-6-27b__lcpp-q2_k");

  await expect(page.getByText("Local Intelligence Index delta")).toBeVisible();
  await expect(page.getByText("VRAM delta")).toBeVisible();
  await expect(page.getByText("tok/s delta")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Qwen3.6-27B" })).toHaveCount(2);
  await expect(page.getByTestId("compare-axis-deltas")).toContainText("Knowledge");
  await expect(page.getByTestId("compare-axis-deltas")).toContainText("Agentic");
  await expect(page.getByTestId("compare-axis-deltas")).toContainText("wins");
  await expect(page.getByRole("link", { name: /Open left model/i })).toBeVisible();
});

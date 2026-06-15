import { readIndexData } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

test("renders the rig-match finder as the home hero", async ({ page }) => {
  await visitRoute(page, "/");

  await expect(page.getByRole("heading", { name: "What can I run?" })).toBeVisible();
  await expect(page.getByText("Synthetic demo rows remain marked; Qwen3.6-27B quant rows are real measurements.")).toBeVisible();
  await expect(page.getByLabel("VRAM tier")).toHaveValue("24");
  await expect(page.getByLabel("Context length")).toHaveValue("8192");
  await expect(page.getByText(/VRAM includes KV cache/i)).toBeVisible();
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /Qwen3 32B.*Q5_K_M/ })).toBeVisible();
  await expect(page.getByText(/frontier ceiling:/i)).toBeVisible();
  await expect(page.getByTestId("rig-match-results").getByText("GPT-5.5")).toHaveCount(0);
  await expect(page.getByTestId("quality-bars")).toBeVisible();
  await expect(page.getByRole("img", { name: /Ranked Quality Bars showing/i })).toBeVisible();
  await expect(page.getByText("frontier line")).toBeVisible();
  await expect(page.getByTestId("quality-vram-scatter")).toHaveCount(0);

  const finderBox = await page.getByTestId("rig-match-finder").boundingBox();
  const barsBox = await page.getByTestId("quality-bars").boundingBox();
  expect(finderBox).not.toBeNull();
  expect(barsBox).not.toBeNull();
  expect(barsBox?.y).toBeGreaterThan(finderBox?.y ?? 0);
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

test("renders the leaderboard and keeps composite sorting deterministic", async ({ page }) => {
  const index = await readIndexData();
  const expectedAscending = [...index.models]
    .sort((left, right) => left.composite.point - right.composite.point)
    .map((model) => model.model_label);
  const expectedDescending = [...expectedAscending].reverse();

  await visitRoute(page, "/");

  const leaderboard = page.getByTestId("full-leaderboard");
  await expect(page.getByRole("heading", { name: "Full leaderboard" })).toBeVisible();
  for (const label of expectedDescending) {
    await expect(leaderboard.getByRole("link", { name: label })).toBeVisible();
  }

  const qwenRow = leaderboard.getByRole("row", { name: /Qwen3\.6-27B/ });
  await expect(qwenRow).toContainText("52.7");
  await expect(qwenRow).toContainText(/±\d+\.\d/);
  await expect(leaderboard.getByText(/Community-reported/).first()).toBeVisible();
  await expect(page.getByText(/sorted for browsing only/i)).toBeVisible();
  await expect(page.getByText(/reasoning lanes are not directly comparable/i)).toBeVisible();

  const modelLinks = leaderboard.locator("tbody tr td:nth-child(2) a");
  const rankCells = leaderboard.locator("tbody tr td:first-child");
  await expect(modelLinks).toHaveText(expectedDescending);
  await expect(rankCells).toHaveCount(expectedDescending.length);

  await leaderboard.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedAscending);

  await leaderboard.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedDescending);

  await capturePage(page, "home-leaderboard");
});

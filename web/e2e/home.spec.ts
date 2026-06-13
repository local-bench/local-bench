import { readIndexData } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

test("renders the rig-match finder as the home hero", async ({ page }) => {
  await visitRoute(page, "/");

  await expect(page.getByRole("heading", { name: "What can I run?" })).toBeVisible();
  await expect(page.getByText("Preview uses synthetic demo data — not real measurements (Track 2 will replace it).")).toBeVisible();
  await expect(page.getByLabel("VRAM tier")).toHaveValue("24");
  await expect(page.getByTestId("rig-match-results").getByRole("row", { name: /Qwen3 32B.*Q5_K_M/ })).toBeVisible();
  await expect(page.getByText(/frontier ceiling:/i)).toBeVisible();
  await expect(page.getByTestId("rig-match-results").getByText("GPT-5.5")).toHaveCount(0);
  await expect(page.getByTestId("quality-vram-scatter")).toBeVisible();

  const finderBox = await page.getByTestId("rig-match-finder").boundingBox();
  const scatterBox = await page.getByTestId("quality-vram-scatter").boundingBox();
  expect(finderBox).not.toBeNull();
  expect(scatterBox).not.toBeNull();
  expect(scatterBox?.y).toBeGreaterThan(finderBox?.y ?? 0);
});

test("renders the leaderboard and keeps composite sorting deterministic", async ({ page }) => {
  const index = await readIndexData();
  const expectedAscending = [...index.models]
    .sort((left, right) => left.composite.point - right.composite.point)
    .map((model) => model.model_label);
  const expectedDescending = [...expectedAscending].reverse();
  const expectedUnrankedMarkers = expectedDescending.map(() => "Unranked");

  await visitRoute(page, "/");

  const leaderboard = page.getByTestId("full-leaderboard");
  await expect(page.getByRole("heading", { name: "Full leaderboard" })).toBeVisible();
  for (const label of expectedDescending) {
    await expect(leaderboard.getByRole("link", { name: label })).toBeVisible();
  }

  const geminiRow = leaderboard.getByRole("row", { name: /Gemini 3\.1 Pro/ });
  await expect(geminiRow).toContainText("94.4");
  await expect(geminiRow).toContainText(/±\d+\.\d/);
  await expect(leaderboard.getByText("Anchor").first()).toBeVisible();
  await expect(leaderboard.getByText(/Community-reported/).first()).toBeVisible();
  await expect(page.getByText(/sorted for browsing only/i)).toBeVisible();
  await expect(page.getByText(/reasoning lanes are not directly comparable/i)).toBeVisible();

  const modelLinks = leaderboard.locator("tbody tr td:nth-child(2) a");
  const rankCells = leaderboard.locator("tbody tr td:first-child");
  await expect(modelLinks).toHaveText(expectedDescending);
  await expect(rankCells).toHaveText(expectedUnrankedMarkers);

  await leaderboard.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedAscending);

  await leaderboard.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedDescending);

  await capturePage(page, "home-leaderboard");
});

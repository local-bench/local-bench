import { readIndexData } from "./data";
import { capturePage, expect, test, visitRoute } from "./fixtures";

const EXPECTED_MODEL_LABELS = [
  "Claude Opus 4.8",
  "Claude Sonnet 4.6",
  "Gemini 3.1 Pro",
  "GPT-5.5",
  "Qwen3.5 9B",
] as const;

test("renders the leaderboard and keeps composite sorting deterministic", async ({ page }) => {
  const index = await readIndexData();
  const expectedAscending = [...index.models]
    .sort((left, right) => left.composite.point - right.composite.point)
    .map((model) => model.model_label);
  const expectedDescending = [...expectedAscending].reverse();
  const expectedUnrankedMarkers = expectedDescending.map(() => "Unranked");

  await visitRoute(page, "/");

  await expect(page.getByRole("heading", { name: "Local AI quality leaderboard" })).toBeVisible();
  for (const label of EXPECTED_MODEL_LABELS) {
    await expect(page.getByRole("link", { name: label })).toBeVisible();
  }

  const geminiRow = page.getByRole("row", { name: /Gemini 3\.1 Pro/ });
  await expect(geminiRow).toContainText("94.4");
  await expect(geminiRow).toContainText(/±\d+\.\d/);
  await expect(page.getByText("Anchor").first()).toBeVisible();
  await expect(page.getByText(/Community-reported/).first()).toBeVisible();
  await expect(page.getByText(/Replicated/i)).toHaveCount(0);
  await expect(page.getByText(/sorted for browsing only/i)).toBeVisible();
  await expect(page.getByText(/reasoning lanes are not directly comparable/i)).toBeVisible();

  const modelLinks = page.locator("tbody tr td:nth-child(2) a");
  const rankCells = page.locator("tbody tr td:first-child");
  await expect(modelLinks).toHaveText(expectedDescending);
  await expect(rankCells).toHaveText(expectedUnrankedMarkers);

  await page.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedAscending);

  await page.getByRole("button", { name: /Composite/ }).click();
  await expect(modelLinks).toHaveText(expectedDescending);

  await capturePage(page, "home-leaderboard");
});

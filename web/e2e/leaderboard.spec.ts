import { expect, test, visitRoute } from "./fixtures";

test("renders the full detailed leaderboard with a Time/answer column", async ({ page }) => {
  await visitRoute(page, "/leaderboard");

  await expect(page.getByRole("heading", { name: "Full leaderboard" })).toBeVisible();
  const leaderboard = page.getByTestId("full-leaderboard");
  await expect(leaderboard).toBeVisible();
  await expect(leaderboard.getByRole("button", { name: "Time/answer" })).toBeVisible();
  await expect(page.getByText(/reasoning lanes are not directly comparable/i)).toBeVisible();
});

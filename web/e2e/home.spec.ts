import { expect, test, visitRoute } from "./fixtures";
import { getCommunityBoardRows } from "../lib/community-data";

test("leads with the graph + unified board, on-ramp below", async ({ page }) => {
  const communityRows = await getCommunityBoardRows();
  await visitRoute(page, "/");

  await expect(page.getByTestId("best-variant-scatter")).toBeVisible();
  await expect(page.getByTestId("best-variant-table")).toHaveCount(0);
  await expect(page.getByTestId("full-leaderboard")).toBeVisible();
  await expect(page.getByTestId("full-leaderboard").locator('tbody tr[data-source="community"]'))
    .toHaveCount(communityRows?.length ?? 0);
  await expect(page.getByTestId("benchmark-onramp")).toBeVisible();
  await expect(page.getByRole("link", { name: /View full leaderboard/i })).toBeVisible();

  const scatterBox = await page.getByTestId("best-variant-scatter").boundingBox();
  const onrampBox = await page.getByTestId("benchmark-onramp").boundingBox();
  expect(scatterBox).not.toBeNull();
  expect(onrampBox).not.toBeNull();
  expect(onrampBox?.y ?? 0).toBeGreaterThan(scatterBox?.y ?? 0);
});

test("keeps homepage content inside the mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await visitRoute(page, "/");

  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.scrollWidth).toBe(viewport.clientWidth);

  const onramp = page.getByTestId("benchmark-onramp");
  const popularButtonWidths = await onramp.locator('a[aria-label$="GGUF repo on Hugging Face"]').evaluateAll((links) =>
    links.flatMap((link) => {
      const button = link.parentElement?.querySelector("button");
      return button === null || button === undefined ? [] : [button.getBoundingClientRect().width];
    }),
  );
  expect(popularButtonWidths.length).toBeGreaterThan(0);
  expect(Math.min(...popularButtonWidths)).toBeGreaterThan(200);

  const scrollCue = page.getByText(/Swipe horizontally for scores and axes/i);
  await expect(scrollCue).toBeVisible();
  await page.setViewportSize({ width: 768, height: 900 });
  await expect(scrollCue).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(scrollCue).toBeVisible();
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

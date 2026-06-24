import { expect, test, visitRoute } from "./fixtures";

// The intro timeline is ~4.7s; wait comfortably past it before asserting the settled state.
const ANIMATION_SETTLE_MS = 5200;
// Layout tolerance (px). Sub-pixel rounding between two reads is expected; a real CLS would be large.
const LAYOUT_TOLERANCE = 2;

test("reduced-motion: logo + tagline show immediately, decorative layers stay hidden", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await visitRoute(page, "/");

  // The real <h1> logo and tagline are part of the static markup, so they are present at first paint
  // with no animation. The decorative thinking/stream layers are display:none under reduced motion.
  await expect(page.getByRole("heading", { level: 1, name: "local-bench" })).toBeVisible();
  await expect(page.getByText("Open weights. Local hardware. Reproducible results.")).toBeVisible();
  await expect(page.getByTestId("home-hero-stream")).toBeHidden();
  await expect(page.getByTestId("home-hero-thinking")).toBeHidden();
});

test("normal motion: settles to a static logo + tagline with the stream faded out", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await visitRoute(page, "/");

  const logo = page.getByRole("heading", { level: 1, name: "local-bench" });
  const tagline = page.getByText("Open weights. Local hardware. Reproducible results.");

  // Logo + tagline are always in the DOM; after the one-shot timeline they are the only visible thing.
  await expect(logo).toBeVisible();
  await page.waitForTimeout(ANIMATION_SETTLE_MS);
  await expect(logo).toBeVisible();
  await expect(tagline).toBeVisible();

  // The stream layer holds its final keyframe (opacity 0) once the animation ends — it does not loop.
  const streamOpacity = await page
    .getByTestId("home-hero-stream")
    .evaluate((node) => getComputedStyle(node).opacity);
  expect(Number(streamOpacity)).toBeLessThan(0.05);

  // The logo's clip-path has fully opened (no residual horizontal mask) by the settled state.
  const logoClip = await logo.evaluate((node) => getComputedStyle(node).clipPath);
  expect(logoClip === "none" || logoClip.includes("inset(0px)") || logoClip === "inset(0px 0px 0px 0px)").toBe(true);
});

test("no layout shift: hero box and the chart below hold position across the animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await visitRoute(page, "/");

  const hero = page.getByTestId("home-hero");
  const chart = page.getByTestId("best-variant-scatter");
  await expect(hero).toBeVisible();
  await expect(chart).toBeVisible();

  const heroBefore = await hero.boundingBox();
  const chartBefore = await chart.boundingBox();
  expect(heroBefore).not.toBeNull();
  expect(chartBefore).not.toBeNull();

  await page.waitForTimeout(ANIMATION_SETTLE_MS);

  const heroAfter = await hero.boundingBox();
  const chartAfter = await chart.boundingBox();
  expect(heroAfter).not.toBeNull();
  expect(chartAfter).not.toBeNull();

  // min-height reserves the hero box, so neither the hero nor the chart top moves as the intro plays.
  expect(Math.abs((heroAfter?.height ?? 0) - (heroBefore?.height ?? 0))).toBeLessThanOrEqual(LAYOUT_TOLERANCE);
  expect(Math.abs((chartAfter?.y ?? 0) - (chartBefore?.y ?? 0))).toBeLessThanOrEqual(LAYOUT_TOLERANCE);
});

test("forced-colors: the logo + tagline remain readable and decorative layers drop out", async ({ page }) => {
  // forced-colors emulation is supported on Chromium; guard so the spec stays portable.
  let supportsForcedColors = true;
  try {
    await page.emulateMedia({ forcedColors: "active" });
  } catch {
    supportsForcedColors = false;
  }
  test.skip(!supportsForcedColors, "forced-colors emulation is unavailable in this environment");

  await visitRoute(page, "/");

  await expect(page.getByRole("heading", { level: 1, name: "local-bench" })).toBeVisible();
  await expect(page.getByText("Open weights. Local hardware. Reproducible results.")).toBeVisible();
  // The grid / thinking / stream chrome is dropped under forced-colors (display:none).
  await expect(page.getByTestId("home-hero-stream")).toBeHidden();
  await expect(page.getByTestId("home-hero-thinking")).toBeHidden();
});

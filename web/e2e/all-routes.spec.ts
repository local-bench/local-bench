import { getAllStaticRoutes } from "./data";
import { test, visitAndCapture } from "./fixtures";

test("all static routes render HTTP 200 without browser runtime failures", async ({ page }) => {
  const routes = await getAllStaticRoutes();
  // The route list grows with the catalog (one page per model + one per run); budget per route
  // instead of a fixed cap that silently expires as models land.
  test.setTimeout(Math.max(90_000, routes.length * 2_000));

  for (const route of routes) {
    await test.step(route.path, async () => {
      await visitAndCapture(page, route.path, route.screenshotName);
    });
  }
});

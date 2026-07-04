import { getAllStaticRoutes } from "./data";
import { test, visitAndCapture } from "./fixtures";

test.setTimeout(90_000);

test("all static routes render HTTP 200 without browser runtime failures", async ({ page }) => {
  const routes = await getAllStaticRoutes();

  for (const route of routes) {
    await test.step(route.path, async () => {
      await visitAndCapture(page, route.path, route.screenshotName);
    });
  }
});

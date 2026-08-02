import { describe, expect, it } from "vitest";
import { onRequest } from "../functions/_middleware";

const MAINTENANCE_MESSAGE =
  "local-bench is being rebuilt around a new, much faster methodology. Every previously published result is preserved and will return with the new site.";

function nextResponse(): Promise<Response> {
  return Promise.resolve(new Response("existing behavior", { status: 200 }));
}

describe("full-dark maintenance mode", () => {
  it("returns the self-contained holding page for page routes when maintenance is enabled", async () => {
    // Given: the deployment override enables full-dark maintenance mode.
    const request = new Request("https://local-bench.ai/families/gemma");

    // When: a visitor requests an HTML page.
    const response = await onRequest({ env: { MAINTENANCE_MODE: "1" }, next: nextResponse, request });
    const body = await response.text();

    // Then: the middleware returns only the specified holding page with retry guidance.
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBe("86400");
    expect(response.headers.get("content-type")).toContain("text/html");
    expect(body).toContain("<title>local-bench</title>");
    expect(body).toContain("<h1>Being rebuilt</h1>");
    expect(body).toContain(`<p>${MAINTENANCE_MESSAGE}</p>`);
    expect(body).toContain("<footer>— the maintainer</footer>");
    expect(body).not.toContain("<script");
    expect(body).not.toMatch(/\s(?:href|src)=/u);
  });

  it.each([
    ["static data", "https://local-bench.ai/data/index.json"],
    ["public API", "https://local-bench.ai/api/health"],
  ])("returns the maintenance JSON shape for %s routes when maintenance is enabled", async (_routeType, url) => {
    // Given: the deployment override enables full-dark maintenance mode.
    const request = new Request(url);

    // When: a machine-readable route is requested.
    const response = await onRequest({ env: { MAINTENANCE_MODE: "1" }, next: nextResponse, request });

    // Then: no v1 payload is exposed and the response uses the maintenance contract.
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBe("86400");
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(await response.json()).toEqual({ message: MAINTENANCE_MESSAGE, status: "maintenance" });
  });

  it("preserves the existing response when maintenance mode is disabled", async () => {
    // Given: neither the source-of-truth flag nor the deployment override enables maintenance.
    const request = new Request("https://local-bench.ai/data/index.json");

    // When: the middleware handles the request.
    const response = await onRequest({ env: {}, next: nextResponse, request });

    // Then: existing routing behavior passes through untouched.
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("existing behavior");
  });
});

import { describe, expect, it } from "vitest";
import { onRequest } from "../functions/_middleware";

function nextResponse(): Promise<Response> {
  return Promise.resolve(new Response("ok", { status: 200 }));
}

describe("private site gate", () => {
  it("allows public requests when private mode is disabled", async () => {
    // Given: the deployment has not enabled the private-site flag.
    const request = new Request("https://local-bench.ai/api/health");

    // When: the middleware handles the request.
    const response = await onRequest({ env: {}, next: nextResponse, request });

    // Then: the app remains reachable.
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("blocks public requests when private mode is enabled", async () => {
    // Given: the deployment is in private prototype mode.
    const request = new Request("https://local-bench.ai/api/health");

    // When: a public visitor requests the app.
    const response = await onRequest({ env: { LOCALBENCH_SITE_PRIVATE: "1" }, next: nextResponse, request });

    // Then: the app is unavailable to the public and should not be cached or indexed.
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-robots-tag")).toBe("noindex");
  });

  it("allows public artifact downloads when private mode is enabled", async () => {
    // Given: private prototype mode is enabled while signed manifests reference public artifacts.
    const request = new Request("https://local-bench.ai/artifacts/agentic/runtime-v1/rootfs.tar.xz");

    // When: the appliance requests an artifact without an owner bypass token.
    const response = await onRequest({ env: { LOCALBENCH_SITE_PRIVATE: "1" }, next: nextResponse, request });

    // Then: middleware passes the same-origin download through unchanged.
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("allows owner smoke checks through the bypass header", async () => {
    // Given: private mode is enabled with an owner bypass token.
    const request = new Request("https://local-bench.ai/api/health", {
      headers: { "x-localbench-bypass": "owner-token" },
    });

    // When: the owner sends the bypass header.
    const response = await onRequest({
      env: { LOCALBENCH_PRIVATE_BYPASS_TOKEN: "owner-token", LOCALBENCH_SITE_PRIVATE: "true" },
      next: nextResponse,
      request,
    });

    // Then: the underlying app still responds.
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("sets a browser bypass cookie from the one-time query token", async () => {
    // Given: private mode is enabled and the owner opens the one-time bypass URL.
    const request = new Request("https://local-bench.ai/?lb_bypass=owner-token");

    // When: the token matches the configured bypass secret.
    const response = await onRequest({
      env: { LOCALBENCH_PRIVATE_BYPASS_TOKEN: "owner-token", LOCALBENCH_SITE_PRIVATE: "1" },
      next: nextResponse,
      request,
    });

    // Then: the request reaches the app and future browser navigation gets a private cookie.
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("lb_private_bypass=");
  });
});

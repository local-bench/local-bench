import { afterEach, describe, expect, it } from "vitest";
import { Miniflare } from "miniflare";
import { onRequest, type ArtifactEnv } from "../functions/artifacts/[[path]]";

const ARTIFACT_PATH = ["agentic", "runtime-v1", "rootfs.tar.xz"] as const;
const ARTIFACT_KEY = `artifacts/${ARTIFACT_PATH.join("/")}`;
const ARTIFACT_BYTES = "0123456789";

type ArtifactTestBucket = ArtifactEnv["PUBLIC_ARTIFACTS"] & {
  put(
    key: string,
    value: string,
    options?: { readonly httpMetadata?: { readonly contentType?: string } },
  ): Promise<unknown>;
};

type ArtifactTestEnv = {
  readonly PUBLIC_ARTIFACTS: ArtifactTestBucket;
};

const miniflares: Miniflare[] = [];

afterEach(async () => {
  await Promise.all(miniflares.map((miniflare) => miniflare.dispose()));
  miniflares.length = 0;
});

describe("public artifact route", () => {
  it("streams an R2 object at the manifest-pinned URL without redirecting", async () => {
    // Given: the runtime artifact exists in the public R2 bucket.
    const env = await createEnv();
    await putArtifact(env);

    // When: the appliance downloads the exact manifest URL.
    const response = await requestArtifact(env);

    // Then: the object bytes stream from the same URL with their stored metadata.
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/x-xz");
    expect(response.headers.get("content-length")).toBe(String(ARTIFACT_BYTES.length));
    expect(response.headers.get("etag")).not.toBeNull();
    expect(response.headers.get("location")).toBeNull();
    expect(await response.text()).toBe(ARTIFACT_BYTES);
  });

  it("returns not_found JSON when the R2 object is missing", async () => {
    // Given: the public R2 bucket does not contain the requested artifact.
    const env = await createEnv();

    // When: the manifest URL is requested.
    const response = await requestArtifact(env);

    // Then: callers receive the stable missing-object contract.
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("rejects methods other than GET and HEAD", async () => {
    // Given: the public artifact route receives a mutation method.
    const env = await createEnv();

    // When: a caller sends POST to an artifact URL.
    const response = await requestArtifact(env, { method: "POST" });

    // Then: the route rejects the method and advertises its read-only surface.
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET, HEAD");
  });

  it("rejects traversal segments without reading R2", async () => {
    // Given: a path attempts to escape the agentic artifact namespace.
    const env = await createEnv();

    // When: the catch-all route receives a parent-directory segment.
    const response = await requestArtifact(env, { path: ["agentic", "..", "manifest.json"] });

    // Then: the route exposes no bucket key information.
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("rejects empty path segments", async () => {
    // Given: a path contains an empty runtime identifier.
    const env = await createEnv();

    // When: the malformed catch-all path reaches the route.
    const response = await requestArtifact(env, { path: ["agentic", "", "manifest.json"] });

    // Then: the route rejects it as not found.
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("rejects keys outside the agentic artifact namespace", async () => {
    // Given: a syntactically safe path targets a different namespace.
    const env = await createEnv();

    // When: the catch-all route receives the non-agentic path.
    const response = await requestArtifact(env, { path: ["release", "runtime-v1", "manifest.json"] });

    // Then: only signed agentic runtime paths are visible.
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("marks public artifacts immutable for one year", async () => {
    // Given: an immutable runtime artifact exists in R2.
    const env = await createEnv();
    await putArtifact(env);

    // When: the artifact is downloaded.
    const response = await requestArtifact(env);

    // Then: browsers and edge caches may retain the content-addressed response.
    expect(response.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
    expect(response.headers.get("accept-ranges")).toBe("bytes");
  });

  it("returns artifact headers without a body for HEAD", async () => {
    // Given: a runtime artifact exists in R2.
    const env = await createEnv();
    await putArtifact(env);

    // When: a caller probes the artifact with HEAD.
    const response = await requestArtifact(env, { method: "HEAD" });

    // Then: metadata matches GET while no bytes are returned.
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/x-xz");
    expect(response.headers.get("content-length")).toBe(String(ARTIFACT_BYTES.length));
    expect(response.headers.get("etag")).not.toBeNull();
    expect(await response.text()).toBe("");
  });

  it("streams a requested byte range with a content-range response", async () => {
    // Given: a large-download-compatible runtime artifact exists in R2.
    const env = await createEnv();
    await putArtifact(env);

    // When: the appliance resumes from a bounded byte range.
    const response = await requestArtifact(env, { headers: { range: "bytes=2-5" } });

    // Then: the route exposes the R2 partial body directly.
    expect(response.status).toBe(206);
    expect(response.headers.get("content-range")).toBe(`bytes 2-5/${ARTIFACT_BYTES.length}`);
    expect(response.headers.get("content-length")).toBe("4");
    expect(await response.text()).toBe("2345");
  });

  it("rejects a malformed byte range", async () => {
    // Given: an artifact exists but the request carries a multi-range header unsupported by R2.
    const env = await createEnv();
    await putArtifact(env);

    // When: the route receives the malformed range.
    const response = await requestArtifact(env, { headers: { range: "bytes=0-1,4-5" } });

    // Then: the invalid boundary input is rejected before the bucket read.
    expect(response.status).toBe(416);
    expect(await response.json()).toEqual({ error: "invalid_range" });
  });
});

async function createEnv(): Promise<ArtifactTestEnv> {
  const miniflare = new Miniflare({
    compatibilityDate: "2026-06-27",
    modules: true,
    r2Buckets: { PUBLIC_ARTIFACTS: "localbench-public-artifacts" },
    script: "export default { fetch() { return new Response('ok'); } }",
  });
  miniflares.push(miniflare);
  return miniflare.getBindings<ArtifactTestEnv>();
}

async function putArtifact(env: ArtifactTestEnv): Promise<void> {
  await env.PUBLIC_ARTIFACTS.put(ARTIFACT_KEY, ARTIFACT_BYTES, {
    httpMetadata: { contentType: "application/x-xz" },
  });
}

type ArtifactRequestOptions = {
  readonly headers?: Readonly<Record<string, string>>;
  readonly method?: string;
  readonly path?: readonly string[];
};

function requestArtifact(env: ArtifactTestEnv, options: ArtifactRequestOptions = {}): Promise<Response> {
  return onRequest({
    env,
    params: { path: options.path ?? ARTIFACT_PATH },
    request: new Request(`https://local-bench.ai/artifacts/${(options.path ?? ARTIFACT_PATH).join("/")}`, {
      ...(options.headers === undefined ? {} : { headers: options.headers }),
      method: options.method ?? "GET",
    }),
  });
}

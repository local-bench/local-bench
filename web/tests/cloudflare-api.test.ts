import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { handleHealth, handleSuiteManifest, handleSuites, type ApiEnv } from "../functions/_lib/api";
import { PUBLIC_SUITES } from "../functions/_lib/suite-catalog";

function env(): ApiEnv {
  return {
    DB: {},
    LOCALBENCH_PUBLIC_BASE_URL: "https://local-bench.ai",
    R2_BUCKET_NAME: "localbench-submissions",
  };
}

describe("Cloudflare backend contract", () => {
  it("reports health without exposing secrets", async () => {
    // Given: the Cloudflare environment bindings exist.
    const testEnv = env();

    // When: the health endpoint is called.
    const response = handleHealth(testEnv);

    // Then: the response is public-safe and confirms the backend surface.
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      service: "localbench",
      status: "ok",
      storage: { d1: true, queue: false, r2: true },
    });
  });

  it("publishes the core-text suite manifest with downloadable hashed files", async () => {
    // Given: the public suite catalog is requested from the production hostname.
    const requestUrl = new URL("https://local-bench.ai/api/suites/core-text-v1/manifest");

    // When: the suite manifest is rendered.
    const response = handleSuiteManifest(env(), requestUrl, { suiteId: "core-text-v1" });

    // Then: clients receive a versioned manifest with hash-pinned file URLs.
    expect(response.status).toBe(200);
    const manifest = await response.json();
    expect(manifest).toMatchObject({
      schema_version: "localbench.suite-manifest.v1",
      suite_id: "core-text-v1",
    });
    expect(manifest.files.map((file: { readonly path: string }) => file.path)).toEqual(
      expect.arrayContaining(["suite.json", "itemsets.lock.json", "mmlu_pro.jsonl", "ifbench.jsonl", "tc_json_v1.jsonl"]),
    );
    expect(manifest.files.every((file: { readonly sha256: string; readonly url: string }) => file.sha256.length === 64 && file.url.startsWith("https://local-bench.ai/suites/core-text-v1/"))).toBe(true);
  });

  it("publishes the released 4-axis suite manifest with the release manifest file", async () => {
    // Given: the released 4-axis suite is requested from the production hostname.
    const suiteId = "suite-v1-partial-text-code-4axis-v1";
    const requestUrl = new URL(`https://local-bench.ai/api/suites/${suiteId}/manifest`);

    // When: the suite manifest is rendered.
    const response = handleSuiteManifest(env(), requestUrl, { suiteId });

    // Then: clients can fetch the release manifest and every file through Pages.
    expect(response.status).toBe(200);
    const manifest = await response.json();
    expect(manifest).toMatchObject({
      schema_version: "localbench.suite-manifest.v1",
      suite_hash: "bf463bf8526baad676f0a87d743f0037fdc8eb50dc4faf6abc374b29833dd558",
      suite_id: suiteId,
    });
    expect(manifest.files.map((file: { readonly path: string }) => file.path)).toEqual(
      expect.arrayContaining(["suite_release_manifest.json", "suite.json", "lcb.jsonl", "mmlu_pro.jsonl", "ifbench.jsonl", "tc_json_v1.jsonl"]),
    );
    expect(manifest.files.every((file: { readonly sha256: string; readonly url: string }) => file.sha256.length === 64 && file.url.startsWith(`https://local-bench.ai/suites/${suiteId}/`))).toBe(true);
  });

  it("publishes the released 5-axis suite manifest without an appworld jsonl", async () => {
    // Given: the released 5-axis suite is requested from the production hostname.
    const suiteId = "suite-v1-text-code-agentic-5axis-v1";
    const requestUrl = new URL(`https://local-bench.ai/api/suites/${suiteId}/manifest`);

    // When: the suite manifest is rendered.
    const response = handleSuiteManifest(env(), requestUrl, { suiteId });

    // Then: clients can fetch the release manifest while appworld_c remains out-of-band.
    expect(response.status).toBe(200);
    const manifest = await response.json();
    const paths = manifest.files.map((file: { readonly path: string }) => file.path);
    expect(manifest).toMatchObject({
      schema_version: "localbench.suite-manifest.v1",
      suite_hash: "de25c8064f2342ef1f59a6a99065f7fe8dd17b389a899f0db3ce197f64f3fbf3",
      suite_id: suiteId,
    });
    expect(paths).toEqual(
      expect.arrayContaining(["suite_release_manifest.json", "suite.json", "lcb.jsonl", "mmlu_pro.jsonl", "ifbench.jsonl", "tc_json_v1.jsonl"]),
    );
    expect(paths).not.toContain("appworld_c.jsonl");
    expect(manifest.files.every((file: { readonly sha256: string; readonly url: string }) => file.sha256.length === 64 && file.url.startsWith(`https://local-bench.ai/suites/${suiteId}/`))).toBe(true);
  });

  it("keeps the suite catalog hashes synchronized with published files", () => {
    // Given: the suite catalog constants drive online fetch-suite verification.
    for (const suite of PUBLIC_SUITES) {
      const suiteRoot = new URL(`../public/suites/${suite.id}/`, import.meta.url);

      // When / Then: every catalog hash matches the file served by Pages.
      for (const file of suite.files) {
        const data = readFileSync(new URL(file.path, suiteRoot));
        expect(createHash("sha256").update(data).digest("hex")).toBe(file.sha256);
        expect(data.byteLength).toBe(file.size);
      }
    }
  });

  it("serves manifest hashes that match the CLI executable directory hash", async () => {
    // Given: fetch-suite verifies the legacy manifest suite_hash against the local directory hash.
    for (const suite of PUBLIC_SUITES) {
      const requestUrl = new URL(`https://local-bench.ai/api/suites/${suite.id}/manifest`);

      // When: the manifest route renders the suite.
      const response = handleSuiteManifest(env(), requestUrl, { suiteId: suite.id });

      // Then: the route serves the same executable directory hash the CLI computes.
      expect(response.status).toBe(200);
      const manifest = await response.json();
      expect(manifest.suite_hash).toBe(executableSuiteHash(suite.id));
      expect(suite.files.map((file) => file.path)).toEqual(expect.arrayContaining([...sha256SumsPaths(suite.id)]));
    }
  });

  it("lists public suites without requiring D1 bootstrap data", async () => {
    // Given / When: the suites endpoint is called before D1 has catalog rows.
    const response = handleSuites(env());

    // Then: the static public suites are still discoverable.
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      suites: expect.arrayContaining([
        expect.objectContaining({ id: "core-text-v1", manifest_url: "https://local-bench.ai/api/suites/core-text-v1/manifest" }),
        expect.objectContaining({
          id: "suite-v1-partial-text-code-4axis-v1",
          manifest_url: "https://local-bench.ai/api/suites/suite-v1-partial-text-code-4axis-v1/manifest",
        }),
        expect.objectContaining({
          id: "suite-v1-text-code-agentic-5axis-v1",
          manifest_url: "https://local-bench.ai/api/suites/suite-v1-text-code-agentic-5axis-v1/manifest",
        }),
      ]),
    });
  });
});

function executableSuiteHash(suiteId: string): string {
  const root = suiteRoot(suiteId);
  const suite = JSON.parse(readFileSync(new URL("suite.json", root), "utf-8"));
  const lock = JSON.parse(readFileSync(new URL("itemsets.lock.json", root), "utf-8"));
  const files = new Set<string>(["suite.json", "itemsets.lock.json"]);
  if (isRecord(lock.files)) {
    for (const file of Object.keys(lock.files)) {
      files.add(file);
    }
  }
  if (isRecord(suite.benches)) {
    for (const bench of Object.values(suite.benches)) {
      if (isRecord(bench) && typeof bench["template"] === "string") {
        files.add(bench["template"]);
      }
    }
  }
  const digest = createHash("sha256");
  for (const file of [...files].sort()) {
    const fileHash = createHash("sha256").update(readFileSync(new URL(file, root))).digest("hex");
    digest.update(file);
    digest.update("\0");
    digest.update(fileHash);
    digest.update("\n");
  }
  return digest.digest("hex");
}

function sha256SumsPaths(suiteId: string): readonly string[] {
  const sumsUrl = new URL("SHA256SUMS", suiteRoot(suiteId));
  if (!existsSync(sumsUrl)) {
    return [];
  }
  return readFileSync(sumsUrl, "utf-8")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => line.split("  ")[1])
    .filter((path): path is string => path !== undefined);
}

function suiteRoot(suiteId: string): URL {
  return new URL(`../public/suites/${suiteId}/`, import.meta.url);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

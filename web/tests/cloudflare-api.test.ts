import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
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
      suite_hash: "b3fc40191c366d87b5537b12daa3d5c3680035238492c47996ab1f1b00d32231",
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
      suite_hash: "5a47282a55621cbb9be4b719c1f9bba2f740d7720ef594fa00e794355cc420f9",
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

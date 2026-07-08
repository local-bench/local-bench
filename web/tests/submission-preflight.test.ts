import { describe, expect, it } from "vitest";
import { onRequestPost as preflight } from "../functions/api/submissions/preflight";
import {
  createEnv,
  jsonRequest,
  resultBundle,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
} from "./submission-test-support";

describe("submission publishability preflight", () => {
  it("accepts a valid one-shot identity envelope without mutating submissions", async () => {
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: false });
    const before = await submissionCount(env);

    const response = await preflight({
      env,
      request: jsonRequest("/api/submissions/preflight", preflightBody()),
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      publishable: true,
      reasons: [],
      suite: {
        suite_manifest_sha256: SUITE_MANIFEST_SHA,
        suite_release_id: SUITE_RELEASE_ID,
      },
    });
    await expect(submissionCount(env)).resolves.toBe(before);
  });

  it("returns publishable false for an unregistered suite pair without issuing a trust decision", async () => {
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: false });
    const body = preflightBody({ suite_manifest_sha256: "0".repeat(64) });

    const response = await preflight({
      env,
      request: jsonRequest("/api/submissions/preflight", body),
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      publishable: false,
      reasons: ["unknown_suite_release"],
    });
    await expect(submissionCount(env)).resolves.toBe(0);
  });

  it("rejects malformed preflight bodies", async () => {
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: false });

    const response = await preflight({
      env,
      request: jsonRequest("/api/submissions/preflight", { source: "one_shot" }),
    });

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({
      code: "invalid_preflight",
    });
  });
});

function preflightBody(
  overrides: Partial<{
    readonly suite_manifest_sha256: string;
    readonly suite_release_id: string;
  }> = {},
): Record<string, unknown> {
  const suiteReleaseId = overrides.suite_release_id ?? SUITE_RELEASE_ID;
  const suiteManifestSha256 = overrides.suite_manifest_sha256 ?? SUITE_MANIFEST_SHA;
  const identity = {
    artifact: {
      filename: "model-q4.gguf",
      quant_label: "Q4_K_M",
      repo_id: "owner/model-gguf",
      revision: "a".repeat(40),
      sha256: "1".repeat(64),
      size_bytes: 2048,
    },
    catalog_model_id: "Qwen/Qwen3.6-27B",
    cli_version: "0.2.5",
    local_only: false,
    publishable: true,
    requested_model: "qwen3-6-27b",
    schema_version: "localbench.one_shot_identity.v1",
    source: "one_shot",
    suite_manifest_sha256: suiteManifestSha256,
    suite_release_id: suiteReleaseId,
  };
  return {
    artifact: identity.artifact,
    catalog_model_id: "Qwen/Qwen3.6-27B",
    cli_version: "0.2.5",
    identity_envelope: identity,
    quant_label: "Q4_K_M",
    result_bundle: resultBundle({
      suiteManifestSha: suiteManifestSha256,
      suiteReleaseId,
    }),
    schema_version: "localbench.publishability_preflight.v1",
    source: "one_shot",
    suite_manifest_sha256: suiteManifestSha256,
    suite_release_id: suiteReleaseId,
  };
}

async function submissionCount(env: Awaited<ReturnType<typeof createEnv>>): Promise<number> {
  const row = await env.DB.prepare("select count(*) as count from submissions").first<{ count: number }>();
  return row?.count ?? 0;
}

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import { rawBundleKey, verifyRawBundle } from "../functions/_lib/submission-storage";

describe("submission raw bundle storage", () => {
  it("hashes the R2 body stream without fetching text", async () => {
    const bundleText = '{"schema_version":"localbench.result_bundle.v1"}';
    const sha = createHash("sha256").update(bundleText).digest("hex");
    let gets = 0;
    const env = storageEnv(async (key) => {
      expect(key).toBe(rawBundleKey(sha));
      gets += 1;
      return r2Object(bundleText);
    });

    await expect(verifyRawBundle(env, sha)).resolves.toEqual({
      kind: "ok",
      sizeBytes: new TextEncoder().encode(bundleText).byteLength,
    });
    expect(gets).toBe(1);
  });

  it("rejects a SHA mismatch from the streamed body without decoding text", async () => {
    const expectedSha = "0".repeat(64);
    let gets = 0;
    const env = storageEnv(async (key) => {
      expect(key).toBe(rawBundleKey(expectedSha));
      gets += 1;
      return r2Object("attacker-authored bytes");
    });

    await expect(verifyRawBundle(env, expectedSha)).resolves.toMatchObject({
      code: "raw_bundle_sha_mismatch",
      kind: "error",
      status: 400,
    });
    expect(gets).toBe(1);
  });

  it("does not structurally scan or parse the bundle during admission", async () => {
    const bundleText = `[${Array.from({ length: 75_001 }, () => "0").join(",")}]`;
    const sha = createHash("sha256").update(bundleText).digest("hex");
    let gets = 0;
    const env = storageEnv(async () => {
      gets += 1;
      return r2Object(bundleText);
    });

    await expect(verifyRawBundle(env, sha)).resolves.toEqual({
      kind: "ok",
      sizeBytes: new TextEncoder().encode(bundleText).byteLength,
    });
    expect(gets).toBe(1);
  });

  it("returns the structured size error when streamed bytes exceed the cap", async () => {
    const chunk = new Uint8Array(1024 * 1024);
    let emitted = 0;
    const env = storageEnv(async () => ({
      body: new ReadableStream<Uint8Array>({
        pull(controller) {
          emitted += 1;
          controller.enqueue(chunk);
        },
      }),
    }));

    await expect(verifyRawBundle(env, "0".repeat(64))).resolves.toEqual({
      code: "bundle_too_large",
      error: "uploaded bundle exceeds the server upload limit",
      kind: "error",
      status: 413,
    });
    expect(emitted).toBeGreaterThanOrEqual(51);
    expect(emitted).toBeLessThanOrEqual(52);
  });

  it("keeps bundle-materializing helpers out of the admission modules", () => {
    const finalizeSource = readFileSync(new URL("../functions/_lib/submission-complete-api.ts", import.meta.url), "utf8");
    const storageSource = readFileSync(new URL("../functions/_lib/submission-storage.ts", import.meta.url), "utf8");
    const canonicalSource = readFileSync(new URL("../functions/_lib/submission-canonical.ts", import.meta.url), "utf8");

    expect(finalizeSource).not.toMatch(/ResultBundleSchema|parseJson|canonicalPayload|validatePendingAdmission/);
    expect(storageSource).not.toMatch(/\.text\(\)|TextDecoder|JSON\.parse|JsonComplexity/);
    expect(canonicalSource).not.toMatch(/canonicalPayloadBytes|canonicalPayloadSha256/);
  });
});

function r2Object(text: string) {
  const bytes = new TextEncoder().encode(text);
  return {
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        const split = Math.floor(bytes.byteLength / 2);
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split));
        controller.close();
      },
    }),
    size: bytes.byteLength,
    text: async () => {
      throw new Error("admission must not call text()");
    },
  };
}

function storageEnv(get: SubmissionApiEnv["SUBMISSIONS"]["get"]): SubmissionApiEnv {
  return {
    DB: {} as SubmissionApiEnv["DB"],
    SUBMISSIONS: {
      delete: async () => undefined,
      get,
      put: async () => undefined,
    },
  };
}

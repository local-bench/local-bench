import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import { rawBundleKey, readRawBundle } from "../functions/_lib/submission-storage";

describe("submission raw bundle storage", () => {
  it("hashes the R2 body stream before fetching text", async () => {
    const bundleText = '{"schema_version":"localbench.result_bundle.v1"}';
    const sha = createHash("sha256").update(bundleText).digest("hex");
    let gets = 0;
    const env = storageEnv(async (key) => {
      expect(key).toBe(rawBundleKey(sha));
      gets += 1;
      return r2Object(bundleText, gets === 1);
    });

    await expect(readRawBundle(env, sha)).resolves.toEqual({
      kind: "ok",
      sizeBytes: new TextEncoder().encode(bundleText).byteLength,
      text: bundleText,
    });
    expect(gets).toBe(2);
  });

  it("rejects a SHA mismatch from the streamed body without decoding text", async () => {
    const expectedSha = "0".repeat(64);
    let gets = 0;
    const env = storageEnv(async (key) => {
      expect(key).toBe(rawBundleKey(expectedSha));
      gets += 1;
      return r2Object("attacker-authored bytes", true);
    });

    await expect(readRawBundle(env, expectedSha)).resolves.toMatchObject({
      code: "raw_bundle_sha_mismatch",
      kind: "error",
      status: 400,
    });
    expect(gets).toBe(1);
  });

  it("rejects structurally explosive JSON during the streamed hash pass", async () => {
    const bundleText = `[${Array.from({ length: 75_001 }, () => "0").join(",")}]`;
    const sha = createHash("sha256").update(bundleText).digest("hex");
    let gets = 0;
    const env = storageEnv(async () => {
      gets += 1;
      return r2Object(bundleText, true);
    });

    await expect(readRawBundle(env, sha)).resolves.toMatchObject({
      code: "invalid_result_bundle",
      kind: "error",
      status: 400,
    });
    expect(gets).toBe(1);
  });
});

function r2Object(text: string, textMustNotBeRead: boolean) {
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
      if (textMustNotBeRead) throw new Error("hash pass must not call text()");
      return text;
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

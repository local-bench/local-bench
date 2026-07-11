import { generateKeyPairSync, sign } from "node:crypto";
import type { D1DatabaseBinding, D1PreparedStatement, SqlValue, SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { canonicalJson } from "../functions/_lib/submission-canonical";
import { RAW_BUNDLE_SHA, TEST_COMMUNITY_GROUP_ID, resultBundle } from "./submission-test-support";

export const FIVE_AXIS_SUITE_RELEASE_ID = "suite-v1-full-exec-6axis-v1";
export const FIVE_AXIS_SUITE_MANIFEST_SHA = "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468";
const FOUR_AXIS_SUITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1";
const FOUR_AXIS_SUITE_MANIFEST_SHA = "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7";
export const TEST_IP = "203.0.113.9";

export type TestKeyPair = {
  readonly publicKeyHex: string;
  readonly signMessage: (message: string) => string;
};

export function communityTicketBody(
  bundleSha: string,
  key: TestKeyPair,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  const timestamp = typeof overrides["timestamp"] === "string" ? overrides["timestamp"] : new Date().toISOString();
  const expectedSuiteReleaseId = valueOrDefault(overrides["expected_suite_release_id"], FIVE_AXIS_SUITE_RELEASE_ID);
  const expectedSuiteManifestSha = valueOrDefault(overrides["expected_suite_manifest_sha256"], FIVE_AXIS_SUITE_MANIFEST_SHA);
  const base: Record<string, unknown> = {
    accepted_suite_terms: true,
    bundle_sha256: bundleSha,
    community_model_group_id: TEST_COMMUNITY_GROUP_ID,
    declared_model_slug: "gemma-4-12b-q4",
    expected_suite_manifest_sha256: expectedSuiteManifestSha,
    expected_suite_release_id: expectedSuiteReleaseId,
    pop: {
      signature: key.signMessage(ticketPopMessage(bundleSha, expectedSuiteReleaseId, expectedSuiteManifestSha, timestamp)),
      timestamp,
    },
    public_key: key.publicKeyHex,
  };
  const { timestamp: _timestamp, ...rest } = overrides;
  return { ...base, ...rest };
}

export function signedResultBundle(
  key: TestKeyPair,
  overrides: Record<string, unknown> = {},
  modelSha256 = "a".repeat(64),
): Record<string, unknown> {
    const base = resultBundle({
      semanticFull: true,
      suiteManifestSha: FIVE_AXIS_SUITE_MANIFEST_SHA,
      suiteReleaseId: FIVE_AXIS_SUITE_RELEASE_ID,
    });
  const manifest = base["manifest"] as Record<string, unknown>;
  const payload = {
    ...base,
    manifest: { ...manifest, model: { file_sha256: modelSha256 } },
    model: { file_sha256: modelSha256 },
    ...overrides,
  };
  return {
    ...payload,
    signature: {
      algorithm: "Ed25519",
      public_key: key.publicKeyHex,
      signature: key.signMessage(canonicalJson(payload)),
    },
  };
}

export function testKeyPair(): TestKeyPair {
  const keyPair = generateKeyPairSync("ed25519");
  const publicKeyDer = keyPair.publicKey.export({ format: "der", type: "spki" });
  return {
    publicKeyHex: Buffer.from(publicKeyDer).subarray(-32).toString("hex"),
    signMessage: (message: string) => sign(null, Buffer.from(message, "utf-8"), keyPair.privateKey).toString("hex"),
  };
}

function ticketPopMessage(bundleSha: string, releaseId: string, manifestSha: string, timestamp: string): string {
  return `localbench.ticket_pop.v1\n${bundleSha}\n${releaseId}\n${manifestSha}\n${timestamp}`;
}

function valueOrDefault(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

export async function sha256Bytes(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", arrayBufferFromBytes(bytes));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function arrayBufferFromBytes(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

export function oversizeEnv(): SubmissionApiEnv {
  const row = ticketRow();
  const bucket = {
    delete: async () => undefined,
    get: async () => ({
      body: new ReadableStream<Uint8Array>({
        start: (controller) => controller.error(new Error("body should not be read")),
      }),
      text: async () => {
        throw new Error("body should not be read");
      },
    }),
    head: async () => ({ size: 67_108_865 }),
    put: async () => undefined,
  };
  return {
    DB: new SingleRowDatabase(row),
    SUBMISSIONS: bucket,
  };
}

class SingleRowDatabase implements D1DatabaseBinding {
  constructor(private readonly row: Record<string, unknown>) {}

  async exec(): Promise<unknown> {
    return undefined;
  }

  prepare(query: string): D1PreparedStatement {
    return new SingleRowStatement(query, this.row);
  }
}

class SingleRowStatement implements D1PreparedStatement {
  private values: readonly SqlValue[] = [];

  constructor(
    private readonly query: string,
    private readonly row: Record<string, unknown>,
  ) {}

  bind(...values: readonly SqlValue[]): D1PreparedStatement {
    this.values = values;
    return this;
  }

  async first(): Promise<Record<string, unknown> | null> {
    const value = this.values[0];
    if (this.query.includes("where raw_bundle_sha256 = ?")) {
      return value === RAW_BUNDLE_SHA ? this.row : null;
    }
    if (this.query.includes("where submission_id = ?")) {
      return value === "ticket_oversize" ? this.row : null;
    }
    return null;
  }

  async run(): Promise<{ readonly success: boolean }> {
    return { success: true };
  }

  async all(): Promise<{ readonly results: readonly Record<string, unknown>[] }> {
    return { results: [] };
  }
}

function ticketRow(): Record<string, unknown> {
  return {
    bundle_schema_version: "localbench.result_bundle.v1",
    created_at: "2026-01-01T00:00:00Z",
    duplicate_of: null,
    expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    origin: "project_anchor",
    projection_sha256: null,
    publish_state: "hidden",
    raw_bundle_r2_key: rawBundleKey(RAW_BUNDLE_SHA),
    raw_bundle_sha256: RAW_BUNDLE_SHA,
    raw_bundle_size_bytes: null,
    run_payload_sha256: null,
    status: "ticketed",
    status_reason: null,
    submission_id: "ticket_oversize",
    submitter_display_name: null,
    submitter_id: "project-anchor",
    suite_manifest_sha256: FOUR_AXIS_SUITE_MANIFEST_SHA,
    suite_release_id: FOUR_AXIS_SUITE_RELEASE_ID,
    ticket_id: "ticket_oversize",
    uploaded_at: null,
  };
}

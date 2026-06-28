import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  handleAdminDecision,
  handleAdminListSubmissions,
  handleAdminVerificationResult,
  handleCompleteSubmission,
  handleCreateTicket,
  handleHealth,
  handleSuiteManifest,
  handleSuites,
  handleSubmissionStatus,
  type ApiEnv,
} from "../functions/_lib/api";
import { CORE_TEXT_SUITE } from "../functions/_lib/suite-catalog";

class FakeD1Result {
  private readonly values: SqlValue[] = [];

  constructor(
    private readonly database: FakeD1Database,
    private readonly sql: string,
  ) {}

  bind(...values: readonly SqlValue[]): FakeD1Result {
    this.values.push(...values);
    return this;
  }

  first(): Record<string, unknown> | null {
    if (this.sql.includes("from submissions") && this.sql.includes("where submission_id")) {
      const submissionId = String(this.values[0] ?? "");
      return this.database.submissions.get(submissionId) ?? null;
    }
    return null;
  }

  run(): { readonly success: true } {
    if (this.sql.includes("insert into submissions")) {
      const [submissionId, publicKey, suiteId, suiteHash, serverNonce, r2Key] = this.values;
      this.database.submissions.set(String(submissionId), {
        bundle_sha256: null,
        manifest_payload_sha256: null,
        public_key: String(publicKey),
        r2_key: String(r2Key),
        server_nonce: String(serverNonce),
        size_bytes: null,
        status: "issued",
        submission_id: String(submissionId),
        suite_hash: String(suiteHash),
        suite_id: String(suiteId),
      });
    }
    if (this.sql.includes("set status = 'uploaded'")) {
      const [bundleSha, manifestSha, size, submissionId] = this.values;
      const row = this.database.submissions.get(String(submissionId));
      if (row !== undefined) {
        this.database.submissions.set(String(submissionId), {
          ...row,
          bundle_sha256: bundleSha,
          manifest_payload_sha256: manifestSha,
          size_bytes: size,
          status: "uploaded",
        });
      }
    }
    if (this.sql.includes("update submissions set status = ?")) {
      const [status, submissionId] = this.values;
      const row = this.database.submissions.get(String(submissionId));
      if (row !== undefined) {
        this.database.submissions.set(String(submissionId), { ...row, status });
      }
    }
    return { success: true };
  }

  all(): { readonly results: readonly Record<string, unknown>[] } {
    if (this.sql.includes("from submissions") && this.sql.includes("where status = ?")) {
      const status = String(this.values[0] ?? "");
      return {
        results: [...this.database.submissions.values()].filter((row) => row["status"] === status),
      };
    }
    return { results: [...this.database.submissions.values()] };
  }
}

class FakeD1Database {
  readonly submissions = new Map<string, Record<string, unknown>>();

  prepare(sql: string): FakeD1Result {
    return new FakeD1Result(this, sql);
  }
}

type SqlValue = string | number | null;

function env(): ApiEnv {
  return {
    ADMIN_API_SECRET: "admin-secret",
    DB: new FakeD1Database(),
    LOCALBENCH_PUBLIC_BASE_URL: "https://local-bench.ai",
    R2_ACCESS_KEY_ID: "test-access-key",
    R2_ACCOUNT_ID: "test-account",
    R2_BUCKET_NAME: "localbench-submissions",
    R2_SECRET_ACCESS_KEY: "test-secret-key",
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

  it("keeps the suite catalog hashes synchronized with published files", () => {
    // Given: the suite catalog constants drive online fetch-suite verification.
    const suiteRoot = new URL("../public/suites/core-text-v1/", import.meta.url);

    // When / Then: every catalog hash matches the file served by Pages.
    for (const file of CORE_TEXT_SUITE.files) {
      const data = readFileSync(new URL(file.path, suiteRoot));
      expect(createHash("sha256").update(data).digest("hex")).toBe(file.sha256);
      expect(data.byteLength).toBe(file.size);
    }
  });

  it("issues a ticket with a direct R2 upload URL and stores only metadata in D1", async () => {
    // Given: a CLI asks for a ticket for the public suite.
    const request = new Request("https://local-bench.ai/api/submissions/tickets", {
      body: JSON.stringify({ public_key: "ab".repeat(32), suite_id: "core-text-v1" }),
      method: "POST",
    });

    // When: the ticket is issued.
    const response = await handleCreateTicket(request, env());

    // Then: the response gives the CLI a short-lived direct upload target.
    expect(response.status).toBe(201);
    const ticket = await response.json();
    expect(ticket).toMatchObject({
      max_bytes: 104_857_600,
      site: "https://local-bench.ai",
      status: "issued",
      upload_method: "r2-presigned-put",
    });
    expect(ticket.submission_id).toMatch(/^sub_/);
    expect(ticket.upload_url).toContain("X-Amz-Signature=");
  });

  it("moves an uploaded submission through review without publishing automatically", async () => {
    // Given: an issued submission exists.
    const testEnv = env();
    const db = testEnv.DB as FakeD1Database;
    db.submissions.set("sub_fixture", {
      bundle_sha256: null,
      manifest_payload_sha256: null,
      r2_key: "submissions/sub_fixture/bundle.lbsub.zip",
      size_bytes: null,
      status: "issued",
      submission_id: "sub_fixture",
    });
    const completeRequest = new Request("https://local-bench.ai/api/submissions/sub_fixture/complete", {
      body: JSON.stringify({ bundle_sha256: "cd".repeat(32), manifest_payload_sha256: "ef".repeat(32), size: 1234 }),
      method: "POST",
    });

    // When: the CLI marks upload complete and an admin accepts it.
    const completeResponse = await handleCompleteSubmission(completeRequest, testEnv, { submissionId: "sub_fixture" });
    const statusResponse = await handleSubmissionStatus(testEnv, { submissionId: "sub_fixture" });
    const decisionResponse = await handleAdminDecision(
      new Request("https://local-bench.ai/api/admin/submissions/sub_fixture/decision", {
        body: JSON.stringify({ decision: "accepted", reason: "fixture passed deterministic re-score" }),
        headers: { "x-localbench-admin-secret": "admin-secret" },
        method: "POST",
      }),
      testEnv,
      { submissionId: "sub_fixture" },
    );

    // Then: publishing remains a later maintainer action.
    expect(completeResponse.status).toBe(200);
    expect((await statusResponse.json()).status).toBe("uploaded");
    expect(await decisionResponse.json()).toMatchObject({ publishable: false, status: "accepted" });
  });

  it("lets an admin verifier pull uploaded bundles and mark them needs_review", async () => {
    // Given: uploaded and already-reviewed submissions exist in D1.
    const testEnv = env();
    const db = testEnv.DB as FakeD1Database;
    db.submissions.set("sub_uploaded", {
      bundle_sha256: "cd".repeat(32),
      manifest_payload_sha256: "ef".repeat(32),
      r2_key: "submissions/sub_uploaded/bundle.lbsub.zip",
      size_bytes: 1234,
      status: "uploaded",
      submission_id: "sub_uploaded",
    });
    db.submissions.set("sub_reviewed", {
      bundle_sha256: "12".repeat(32),
      manifest_payload_sha256: "34".repeat(32),
      r2_key: "submissions/sub_reviewed/bundle.lbsub.zip",
      size_bytes: 5678,
      status: "needs_review",
      submission_id: "sub_reviewed",
    });

    // When: the verifier lists pending uploads and records a verification artifact.
    const listResponse = await handleAdminListSubmissions(
      new Request("https://local-bench.ai/api/admin/submissions?status=uploaded", {
        headers: { "x-localbench-admin-secret": "admin-secret" },
      }),
      testEnv,
    );
    const verificationResponse = await handleAdminVerificationResult(
      new Request("https://local-bench.ai/api/admin/submissions/sub_uploaded/verification", {
        body: JSON.stringify({ result_r2_key: "verification/sub_uploaded.json", status: "needs_review" }),
        headers: { "x-localbench-admin-secret": "admin-secret" },
        method: "POST",
      }),
      testEnv,
      { submissionId: "sub_uploaded" },
    );

    // Then: only uploaded submissions are handed to the verifier and publishing stays manual.
    const listed = await listResponse.json();
    expect(listed.submissions).toHaveLength(1);
    expect(listed.submissions[0]).toMatchObject({ r2_key: "submissions/sub_uploaded/bundle.lbsub.zip", status: "uploaded" });
    expect(listed.submissions[0].download_url).toContain("X-Amz-Signature=");
    expect(await verificationResponse.json()).toMatchObject({
      publishable: false,
      status: "needs_review",
      submission_id: "sub_uploaded",
    });
  });

  it("lists public suites without requiring D1 bootstrap data", async () => {
    // Given / When: the suites endpoint is called before D1 has catalog rows.
    const response = handleSuites(env());

    // Then: the static public suite is still discoverable.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      suites: [{ id: "core-text-v1", manifest_url: "https://local-bench.ai/api/suites/core-text-v1/manifest" }],
    });
  });
});

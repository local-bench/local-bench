import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare } from "miniflare";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { onRequestPost as applyDecision } from "../functions/api/admin/submissions/[submissionId]/decision";
import { onRequestPost as applyVerification } from "../functions/api/admin/submissions/[submissionId]/verification";
import type { SubmissionApiEnv } from "../functions/_lib/submission-api";

const MIGRATION = readFileSync(new URL("../migrations/0002_submission_slice_index.sql", import.meta.url), "utf-8");
const ADMIN_SECRET = "test-admin-secret";
const PROJECTION_SHA = "b".repeat(64);
const SUITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1";
const SUITE_MANIFEST_SHA = "b3fc40191c366d87b5537b12daa3d5c3680035238492c47996ab1f1b00d32231";
const RESULT_BUNDLE = resultBundle();
const RESULT_BUNDLE_JSON = JSON.stringify(RESULT_BUNDLE);
const RAW_BUNDLE_SHA = sha256Hex(RESULT_BUNDLE_JSON);

const miniflares: Miniflare[] = [];

afterEach(async () => {
  await Promise.all(miniflares.map((miniflare) => miniflare.dispose()));
  miniflares.length = 0;
});

describe("submission route contracts", () => {
  it("returns disabled when ticket issuance lacks the admin secret binding", async () => {
    // Given: D1/R2 exist but ADMIN_API_SECRET is intentionally absent.
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: true });

    // When: the project-anchor ticket route is called.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", ticketRequest()),
    });

    // Then: the route degrades clearly without requiring a secret to build.
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({
      code: "admin_api_disabled",
      error: "submission ticket issuance is disabled",
    });
  });

  it("issues a submission envelope and stores a ticketed D1 pointer row", async () => {
    // Given: a test admin secret binding and local D1 migration.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });

    // When: an admin issues a project-anchor ticket for a known bundle hash.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", ticketRequest(), {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: the response is a submission_envelope_v1, not a scoring artifact.
    expect(response.status).toBe(201);
    const envelope = await response.json();
    expect(envelope).toMatchObject({
      accepted_suite_terms: true,
      allowed_schema: "localbench.result_bundle.v1",
      bundle_sha256: RAW_BUNDLE_SHA,
      expected_suite_manifest_sha256: SUITE_MANIFEST_SHA,
      expected_suite_release_id: SUITE_RELEASE_ID,
      max_upload_bytes: 104_857_600,
      one_use: true,
      origin: "project_anchor",
      schema_version: "localbench.submission_envelope.v1",
      submitter_id: "project-anchor",
    });
    expect(envelope.ticket_id).toMatch(/^ticket_/);
    expect(envelope.expiry).toMatch(/Z$/);

    const row = await env.DB.prepare(
      "select status, raw_bundle_sha256, raw_bundle_r2_key from submissions where ticket_id = ?",
    )
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({
      raw_bundle_r2_key: `submissions/raw/${RAW_BUNDLE_SHA}.json`,
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      status: "ticketed",
    });
  });

  it("returns a signed content-addressed R2 PUT target against mock R2", async () => {
    // Given: a ticketed row and fake R2 signing credentials.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);

    // When: the ticket holder requests the upload target.
    const response = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: envelope.ticket_id,
      }),
    });

    // Then: the signed URL points at the private localbench-submissions object key.
    expect(response.status).toBe(200);
    const target = await response.json();
    expect(target).toMatchObject({
      bucket: "localbench-submissions",
      content_sha256: RAW_BUNDLE_SHA,
      method: "PUT",
      r2_key: `submissions/raw/${RAW_BUNDLE_SHA}.json`,
    });
    expect(target.upload_url).toContain("X-Amz-Signature=");
    expect(target.upload_url).toContain(`/localbench-submissions/submissions/raw/${RAW_BUNDLE_SHA}.json`);
  });

  it("returns disabled when upload signing credentials are absent", async () => {
    // Given: a ticketed row exists but R2 signing credentials are intentionally absent.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: false });
    const envelope = await issueEnvelope(env);

    // When: the ticket holder requests a signed upload target.
    const response = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: envelope.ticket_id,
      }),
    });

    // Then: live upload signing is clearly disabled without requiring credentials locally.
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({
      code: "r2_signing_disabled",
      error: "R2 upload signing is disabled",
    });
  });

  it("finalizes uploaded bundles idempotently by raw_bundle_sha256", async () => {
    // Given: a ticketed row and the raw result_bundle_v1 bytes in mock R2.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);

    // When: the CLI completes the same uploaded bundle twice.
    const first = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });
    const second = await completeSubmission({
      env,
      params: { submissionId: `sub_duplicate_${envelope.ticket_id}` },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: both responses identify the same pending-verification row and D1 has no duplicate.
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    const firstBody = await first.json();
    const secondBody = await second.json();
    expect(firstBody).toMatchObject({
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      status: "pending_verification",
      submission_id: envelope.ticket_id,
    });
    expect(secondBody).toEqual(firstBody);
    const count = await env.DB.prepare("select count(*) as count from submissions where raw_bundle_sha256 = ?")
      .bind(RAW_BUNDLE_SHA)
      .first();
    expect(count).toMatchObject({ count: 1 });
  });

  it("rejects uploaded bundles with removed or mismatched result fields", async () => {
    // Given: a ticketed row and a legacy bundle with removed top-level score fields.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const badBundle = { ...resultBundle(), composite: 0.9, schema_version: "localbench.run.v1" };
    const badBundleJson = JSON.stringify(badBundle);
    const badBundleSha = sha256Hex(badBundleJson);
    const envelope = await issueEnvelope(env, badBundleSha);
    await env.SUBMISSIONS.put(
      `submissions/raw/${badBundleSha}.json`,
      badBundleJson,
    );

    // When: the complete route validates the uploaded object.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: badBundleSha,
        size_bytes: 1234,
      }),
    });

    // Then: the old schema and removed fields are rejected before status changes.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      code: "invalid_result_bundle",
      error: "uploaded bundle does not match result_bundle_v1",
    });
    const row = await env.DB.prepare("select status from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "ticketed" });
  });

  it("applies verifier status updates and keeps publication as a separate step", async () => {
    // Given: a pending-verification submission and a verifier-produced status update.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: 1234,
      }),
    });
    const update = statusUpdate("accepted");

    // When: the admin verification route applies the offline verifier status update.
    const response = await applyVerification({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/admin/submissions/${envelope.ticket_id}/verification`, update, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: D1 stores only projection/index pointers and leaves publish_state hidden.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      projection_sha256: PROJECTION_SHA,
      publish_state: "hidden",
      status: "accepted",
      submission_id: envelope.ticket_id,
    });
    const row = await env.DB.prepare(
      "select status, publish_state, projection_sha256, projection_r2_key, validator_version, validator_commit, validated_at from submissions where submission_id = ?",
    )
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({
      projection_r2_key: `projections/${envelope.ticket_id}/${PROJECTION_SHA}.json`,
      projection_sha256: PROJECTION_SHA,
      publish_state: "hidden",
      status: "accepted",
      validated_at: "2026-06-30T00:00:00Z",
      validator_commit: "440f540",
      validator_version: "localbench.submission-validator.v1",
    });
  });

  it("flips publish_state only through the separate admin decision step", async () => {
    // Given: an accepted submission hidden from public boards.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.DB.prepare("update submissions set status = 'accepted', projection_sha256 = ? where submission_id = ?")
      .bind(PROJECTION_SHA, envelope.ticket_id)
      .run();

    // When: an admin explicitly moves the row to preview.
    const response = await applyDecision({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(
        `/api/admin/submissions/${envelope.ticket_id}/decision`,
        { publish_state: "preview" },
        { "x-localbench-admin-secret": ADMIN_SECRET },
      ),
    });

    // Then: the row is preview-visible without changing verifier status.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "preview",
      status: "accepted",
      submission_id: envelope.ticket_id,
    });
  });
});

type TestEnvOptions = {
  readonly includeAdminSecret: boolean;
  readonly includeR2Secrets: boolean;
};

type IssuedEnvelope = {
  readonly ticket_id: string;
};

async function createEnv(options: TestEnvOptions): Promise<SubmissionApiEnv> {
  const miniflare = new Miniflare({
    compatibilityDate: "2026-06-27",
    d1Databases: { DB: "localbench-test" },
    modules: true,
    r2Buckets: { SUBMISSIONS: "localbench-submissions" },
    script: "export default { fetch() { return new Response('ok'); } }",
  });
  miniflares.push(miniflare);
  const bindings = await miniflare.getBindings<SubmissionApiEnv>();
  for (const statement of MIGRATION.split(";").map((part) => part.trim()).filter((part) => part.length > 0)) {
    await bindings.DB.prepare(statement).run();
  }
  return {
    ...bindings,
    LOCALBENCH_PUBLIC_BASE_URL: "https://local-bench.ai",
    ...(options.includeAdminSecret ? { ADMIN_API_SECRET: ADMIN_SECRET } : {}),
    ...(options.includeR2Secrets
      ? {
          R2_ACCESS_KEY_ID: "test-access-key",
          R2_ACCOUNT_ID: "test-account",
          R2_BUCKET_NAME: "localbench-submissions",
          R2_SECRET_ACCESS_KEY: "test-secret-key",
        }
      : {}),
  };
}

async function issueEnvelope(env: SubmissionApiEnv, rawBundleSha = RAW_BUNDLE_SHA): Promise<IssuedEnvelope> {
  const response = await issueTicket({
    env,
    request: jsonRequest("/api/submissions/tickets", ticketRequest(rawBundleSha), {
      "x-localbench-admin-secret": ADMIN_SECRET,
    }),
  });
  expect(response.status).toBe(201);
  const body = await response.json();
  if (!isIssuedEnvelope(body)) {
    throw new Error("ticket response did not include ticket_id");
  }
  return body;
}

function ticketRequest(rawBundleSha = RAW_BUNDLE_SHA): Record<string, unknown> {
  return {
    accepted_suite_terms: true,
    bundle_sha256: rawBundleSha,
    declared_model_slug: "gemma-4-12b-q4",
    submitter_id: "project-anchor",
  };
}

function jsonRequest(path: string, body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://local-bench.ai${path}`, {
    body: JSON.stringify(body),
    headers: { "content-type": "application/json", ...headers },
    method: "POST",
  });
}

function resultBundle(): Record<string, unknown> {
  return {
    axis_status: {},
    benches: {},
    conformance: {},
    headline_complete: false,
    items: [],
    manifest: {
      integrity: { publishable: true },
      provenance: { localbench_repo_commit: "440f540" },
      suite: {
        coverage_profile_id: "partial-text-code-4axis-v1",
        suite_manifest_sha256: SUITE_MANIFEST_SHA,
        suite_release_id: SUITE_RELEASE_ID,
      },
    },
    model: {},
    producer: "localbench-cli",
    run_finished_at: "2026-06-30T00:00:01Z",
    run_started_at: "2026-06-30T00:00:00Z",
    schema_version: "localbench.result_bundle.v1",
    scores: {
      headline_score: null,
      known_headline_contribution: 0.3737,
      measured_headline_weight: 0.5,
      missing_headline_weight: 0.5,
      partial_composite: 0.7473,
      partial_composite_scope: "measured_headline_axes",
      rank_scope: "partial-text-code-4axis-v1",
    },
    serving_mode: "external_openai_compatible_endpoint",
    tier: "standard",
    totals: {},
    warnings: [],
  };
}

function statusUpdate(status: "accepted" | "rejected"): Record<string, unknown> {
  return {
    accepted: status === "accepted",
    blocking_reasons: [],
    projection_path: "out/projection.json",
    projection_sha256: PROJECTION_SHA,
    raw_bundle_sha256: RAW_BUNDLE_SHA,
    reason: "publishable",
    schema_version: "localbench.submission_status_update.v1",
    status,
    validated_at: "2026-06-30T00:00:00Z",
    validator_commit: "440f540",
    validator_version: "localbench.submission-validator.v1",
  };
}

function isIssuedEnvelope(value: unknown): value is IssuedEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "ticket_id" in value &&
    typeof value.ticket_id === "string"
  );
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

import { describe, expect, it } from "vitest";
import { onRequestGet as listAdminSubmissions } from "../functions/api/admin/submissions";
import { onRequestGet as getSubmissionStatus } from "../functions/api/submissions/[submissionId]";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import {
  ADMIN_SECRET,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  SUITE_RELEASE_ID,
  completeProjection,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
  resultBundle,
  sha256Hex,
} from "./submission-test-support";

describe("submission finalize route contracts", () => {
  it("finalizes uploaded bundles idempotently for the same submission id", async () => {
    // Given: a ticketed row and the raw result_bundle_v1 bytes in mock R2.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);

    // When: the CLI completes the same uploaded bundle twice.
    const first = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });
    const second = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: both responses identify the same published row and D1 has no duplicate.
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    const firstBody = await first.json();
    const secondBody = await second.json();
    expect(firstBody).toMatchObject({
      status: "published",
      submission_id: envelope.ticket_id,
    });
    expect(secondBody).toEqual(firstBody);
    const count = await env.DB.prepare("select count(*) as count from submissions where raw_bundle_sha256 = ?")
      .bind(RAW_BUNDLE_SHA)
      .first();
    expect(count).toMatchObject({ count: 1 });
  });

  it("publishes from the pinned client projection without re-scoring raw bundle claims", async () => {
    // Given: a ticket expects the released 4-axis suite, but the uploaded bundle names a different suite.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const mismatchedBundle = resultBundle({ suiteReleaseId: "suite-v1-other-release" });
    const mismatchedBundleJson = JSON.stringify(mismatchedBundle);
    const mismatchedBundleSha = sha256Hex(mismatchedBundleJson);
    const envelope = await issueEnvelope(env, mismatchedBundleSha);
    await env.SUBMISSIONS.put(`submissions/raw/${mismatchedBundleSha}.json`, mismatchedBundleJson);

    // When: the complete route verifies the raw content address and the separately supplied projection.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(mismatchedBundleSha, "project_anchor"),
        raw_bundle_sha256: mismatchedBundleSha,
        size_bytes: mismatchedBundleJson.length,
      }),
    });

    // Then: admission succeeds without parsing or re-scoring attacker-authored bundle claims.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
    const row = await env.DB.prepare("select status, suite_release_id from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "published", suite_release_id: SUITE_RELEASE_ID });
  });

  it("rejects legacy tickets without the required suite pins without deleting the row", async () => {
    // Given: an older/manual ticket row stores null expected suite fields.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env, RAW_BUNDLE_SHA, {
      expected_suite_manifest_sha256: null,
      expected_suite_release_id: null,
    });
    const ticketRow = await env.DB.prepare(
      "select suite_release_id, suite_manifest_sha256 from submissions where submission_id = ?",
    )
      .bind(envelope.ticket_id)
      .first();
    expect(ticketRow).toMatchObject({ suite_manifest_sha256: null, suite_release_id: null });
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);

    // When: the uploaded bundle has the standard released suite.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: the legacy row remains readable but cannot enter the complete ranked board.
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      code: "schema_violation",
      status: "rejected",
      submission_id: envelope.ticket_id,
    });
  });

  it("returns the contract-v2 public submission shape from the status route", async () => {
    // Given: a finalized contract-v2 submission row exists.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // When: the CLI polls the public status route.
    const response = await getSubmissionStatus({
      env,
      params: { submissionId: envelope.ticket_id },
    });

    // Then: the route uses the public store contract without exposing storage keys.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      bundle_schema_version: "localbench.result_bundle.v1",
      duplicate_of: null,
      expires_at: null,
      publish_state: "published",
      status: "published",
      submission_id: envelope.ticket_id,
    });
    expect(body).not.toHaveProperty("raw_bundle_r2_key");
    expect(body).not.toHaveProperty("raw_bundle_sha256");
    expect(body).not.toHaveProperty("r2_key");
    expect(body).not.toHaveProperty("bundle_sha256");
    expect(body).not.toHaveProperty("created_at");
  });

  it("lists contract-v2 submissions from the admin route", async () => {
    // Given: one directly published contract-v2 row and an admin secret.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // When: an admin lists published rows.
    const response = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions?status=published", {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: the list endpoint returns public-safe submission projections ordered for verifier work.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.submissions).toEqual([
      expect.objectContaining({
        duplicate_of: null,
        expires_at: null,
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        status: "published",
        submission_id: envelope.ticket_id,
      }),
    ]);
    expect(body.submissions[0]).not.toHaveProperty("raw_bundle_r2_key");
  });

  it("lists ticketed submissions with creation timestamps from the admin route", async () => {
    // Given: one freshly issued ticketed row and an admin secret.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);

    // When: an admin lists ticketed rows before upload completion.
    const response = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions?status=ticketed", {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: the admin queue row exposes an ISO creation timestamp without storage keys.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.submissions).toEqual([
      expect.objectContaining({
        created_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/),
        expires_at: expect.any(String),
        status: "ticketed",
        submission_id: envelope.ticket_id,
      }),
    ]);
    expect(body.submissions[0]).not.toHaveProperty("raw_bundle_r2_key");
  });

});

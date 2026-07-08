import { describe, expect, it, vi } from "vitest";
import { onRequestGet as listAdminSubmissions } from "../functions/api/admin/submissions";
import { onRequestGet as getSubmissionStatus } from "../functions/api/submissions/[submissionId]";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import {
  ADMIN_SECRET,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
  migrationContractV2WithoutTier,
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
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });
    const second = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
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

  it("rejects uploaded bundles whose suite release does not match the ticket expectation", async () => {
    // Given: a ticket expects the released 4-axis suite, but the uploaded bundle names a different suite.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const mismatchedBundle = resultBundle({ suiteReleaseId: "suite-v1-other-release" });
    const mismatchedBundleJson = JSON.stringify(mismatchedBundle);
    const mismatchedBundleSha = sha256Hex(mismatchedBundleJson);
    const envelope = await issueEnvelope(env, mismatchedBundleSha);
    await env.SUBMISSIONS.put(`submissions/raw/${mismatchedBundleSha}.json`, mismatchedBundleJson);

    // When: the complete route validates the uploaded bundle against the ticket row.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: mismatchedBundleSha,
        size_bytes: mismatchedBundleJson.length,
      }),
    });

    // Then: finalization rejects the wrong suite before the pending-verification update.
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      code: "suite_mismatch",
      error: "uploaded bundle suite does not match submission ticket",
    });
    const row = await env.DB.prepare("select status from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "ticketed" });
  });

  it("allows finalize when the ticket intentionally carries no suite expectation", async () => {
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
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: the legacy/null expectation path preserves the existing successful behavior.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      status: "pending_verification",
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
      publish_state: "hidden",
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      status: "pending_verification",
      submission_id: envelope.ticket_id,
    });
    expect(body).not.toHaveProperty("raw_bundle_r2_key");
    expect(body).not.toHaveProperty("r2_key");
    expect(body).not.toHaveProperty("bundle_sha256");
    expect(body).not.toHaveProperty("created_at");
  });

  it("lists contract-v2 submissions from the admin route", async () => {
    // Given: one pending-verification contract-v2 row and an admin secret.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // When: an admin lists rows awaiting verification.
    const response = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions?status=pending_verification", {
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
        status: "pending_verification",
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

  it("logs and returns a structured 500 when finalize hits a drifted D1 schema", async () => {
    // Given: local D1 has the contract-v2 shape except for the tier column used by markPendingVerification.
    const env = await createEnv({
      includeAdminSecret: true,
      includeR2Secrets: true,
      migrations: [migrationContractV2WithoutTier()],
    });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    try {
      // When: finalization reaches the exact pending-verification update.
      const response = await completeSubmission({
        env,
        params: { submissionId: envelope.ticket_id },
        request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
          raw_bundle_sha256: RAW_BUNDLE_SHA,
          size_bytes: RESULT_BUNDLE_JSON.length,
        }),
      });

      // Then: the route keeps the CLI response contract and emits a structured breadcrumb.
      expect(response.status).toBe(500);
      expect(await response.json()).toMatchObject({
        code: "submission_finalize_failed",
        error: "submission finalization failed",
      });
      expect(errorSpy).toHaveBeenCalledWith(
        "submission_finalize_failed",
        expect.objectContaining({
          leg: "mark_pending_verification",
          route: "POST /api/submissions/:submissionId/complete",
          submission_id: envelope.ticket_id,
          error: expect.objectContaining({
            message: expect.stringContaining("tier"),
          }),
        }),
      );
    } finally {
      errorSpy.mockRestore();
    }
  });
});

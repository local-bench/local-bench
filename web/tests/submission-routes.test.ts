import { describe, expect, it } from "vitest";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as applyDecision } from "../functions/api/admin/submissions/[submissionId]/decision";
import {
  ADMIN_SECRET,
  PROJECTION_SHA,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  completeProjection,
  createEnv,
  issueEnvelope,
  jsonRequest,
  ticketRequest,
} from "./submission-test-support";

describe("submission route contracts", () => {
  it("treats ticket issuance without the admin header as the public community path", async () => {
    // Given: D1/R2 exist but ADMIN_API_SECRET is intentionally absent.
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: true });

    // When: the ticket route is called without an admin secret.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", ticketRequest()),
    });

    // Then: the route uses the community contract instead of issuing an admin ticket.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      code: "invalid_ticket_request",
      error: "invalid submission ticket request",
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

    // Then: the response is a submission_envelope_v2, not a scoring artifact.
    expect(response.status).toBe(201);
    const envelope = await response.json();
    expect(envelope).toMatchObject({
      accepted_suite_terms: true,
      allowed_schema: "localbench.result_bundle.v1",
      bundle_sha256: RAW_BUNDLE_SHA,
      expected_suite_manifest_sha256: SUITE_MANIFEST_SHA,
      expected_suite_release_id: SUITE_RELEASE_ID,
      max_upload_bytes: 52_428_800,
      one_use: true,
      origin: "project_anchor",
      schema_version: "localbench.submission_envelope.v2",
      submitter_id: "project-anchor",
    });
    expect(envelope.ticket_id).toMatch(/^ticket_/);
    expect(envelope.expires_at).toMatch(/Z$/);
    expect(envelope.expiry).toMatch(/Z$/);

    const row = await env.DB.prepare(
      "select status, origin, raw_bundle_sha256, raw_bundle_r2_key, expires_at from submissions where ticket_id = ?",
    )
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({
      expires_at: envelope.expires_at,
      origin: "project_anchor",
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
        size_bytes: RESULT_BUNDLE_JSON.length,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
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
    expect(target.upload_headers).toEqual({
      "content-length": String(RESULT_BUNDLE_JSON.length),
      "if-none-match": "*",
    });
    expect(target.upload_url).not.toContain("x-amz-checksum");
  });

  it("verifies the declared bundle SHA from uploaded bytes before admission", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env, RAW_BUNDLE_SHA, {}, 23);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, "attacker-authored bytes");

    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: 23,
        upload_capability: envelope.upload_capability,
      }),
    });

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "raw_bundle_sha_mismatch" });
    const row = await env.DB.prepare("select status, uploaded_at from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "ticketed", uploaded_at: null });
  });

  it("keeps public ticket ids from authorizing upload overwrite", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);

    const missingCapability = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
        ticket_id: envelope.ticket_id,
      }),
    });
    const wrongCapability = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
        ticket_id: envelope.ticket_id,
        upload_capability: `upload_${"f".repeat(32)}`,
      }),
    });
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    const overwrite = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
      }),
    });

    expect(missingCapability.status).toBe(400);
    expect(wrongCapability.status).toBe(404);
    expect(overwrite.status).toBe(409);
    expect(await overwrite.json()).toMatchObject({ code: "raw_bundle_exists" });
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
        size_bytes: RESULT_BUNDLE_JSON.length,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
      }),
    });

    // Then: live upload signing is clearly disabled without requiring credentials locally.
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({
      code: "r2_signing_disabled",
      error: "R2 upload signing is disabled",
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

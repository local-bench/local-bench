import { describe, expect, it } from "vitest";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as applyDecision } from "../functions/api/admin/submissions/[submissionId]/decision";
import { onRequestPost as applyVerification } from "../functions/api/admin/submissions/[submissionId]/verification";
import { onRequestGet as listAdminSubmissions } from "../functions/api/admin/submissions";
import {
  ADMIN_SECRET,
  PROJECTION_SHA,
  PROJECTION_OBJECT_SHA,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
  statusUpdate,
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
      max_upload_bytes: 67_108_864,
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
      "if-none-match": "*",
    });
    expect(target.upload_url).not.toContain("x-amz-checksum");
  });

  it("verifies the declared bundle SHA from uploaded bytes before admission", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, "attacker-authored bytes");

    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: 23,
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
        ticket_id: envelope.ticket_id,
      }),
    });
    const wrongCapability = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: envelope.ticket_id,
        upload_capability: `upload_${"f".repeat(32)}`,
      }),
    });
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
    const overwrite = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
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
      "select status, publish_state, projection_sha256, projection_object_sha256, projection_r2_key, validator_version, validator_commit, validated_at from submissions where submission_id = ?",
    )
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({
      projection_object_sha256: PROJECTION_OBJECT_SHA,
      projection_r2_key: `projections/sha256/${PROJECTION_OBJECT_SHA}.json`,
      projection_sha256: PROJECTION_SHA,
      publish_state: "hidden",
      status: "accepted",
      validated_at: "2026-06-30T00:00:00Z",
      validator_commit: "440f540",
      validator_version: "localbench.submission-validator.v1",
    });
  });

  it("enforces FIFO cohort order for admin verification unless override is explicit", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const rows = [
      { id: "pending_oldest", sha: "1".repeat(64), uploaded: "2026-07-10 00:00:01" },
      { id: "pending_second", sha: "2".repeat(64), uploaded: "2026-07-10 00:00:02" },
    ];
    for (const row of rows) {
      await env.DB.prepare(
        `insert into submissions (
          submission_id, origin, submitter_id, ticket_id, status, raw_bundle_sha256,
          idempotency_key, publish_state, uploaded_at, suite_release_id, suite_manifest_sha256
        ) values (?, 'community', ?, ?, 'pending_verification', ?, ?, 'hidden', ?, ?, ?)`,
      ).bind(row.id, `public_key:${row.sha}`, row.id, row.sha, row.sha, row.uploaded, SUITE_RELEASE_ID, SUITE_MANIFEST_SHA).run();
    }
    const second = rows[1] as { id: string; sha: string; uploaded: string };
    const secondUpdate = statusUpdate("accepted", second.sha);

    const refused = await applyVerification({
      env,
      params: { submissionId: second.id },
      request: jsonRequest(`/api/admin/submissions/${second.id}/verification`, secondUpdate, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });
    const listed = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions?status=pending_verification", {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });
    const overridden = await applyVerification({
      env,
      params: { submissionId: second.id },
      request: jsonRequest(`/api/admin/submissions/${second.id}/verification?override=true`, secondUpdate, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    expect(refused.status).toBe(409);
    expect(await refused.json()).toMatchObject({ code: "fifo_policy_violation", position: 2 });
    expect((await listed.json()).submissions.map((row: { submission_id: string }) => row.submission_id)).toEqual([
      "pending_oldest",
      "pending_second",
    ]);
    expect(overridden.status).toBe(200);
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

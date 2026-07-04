import { describe, expect, it } from "vitest";
import { handleFinalizeSubmission } from "../functions/_lib/submission-api";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import {
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  createEnv,
  issueEnvelope,
  jsonRequest,
  resultBundle,
  sha256Hex,
} from "./submission-test-support";
import {
  TEST_IP,
  communityTicketBody,
  oversizeEnv,
  sha256Bytes,
  signedResultBundle,
  testKeyPair,
} from "./submission-contract-v2-support";

describe("submission contract v2 upload and complete routes", () => {
  it("rejects expired tickets at request-upload and complete", async () => {
    // Given: an issued ticket is past its server-side expiry.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.DB.prepare("update submissions set expires_at = ? where submission_id = ?")
      .bind(new Date(Date.now() - 60_000).toISOString(), envelope.ticket_id)
      .run();
    await env.SUBMISSIONS.put(rawBundleKey(RAW_BUNDLE_SHA), RESULT_BUNDLE_JSON);

    // When: the client tries both upload-target and completion legs.
    const uploadResponse = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: envelope.ticket_id,
      }),
    });
    const completeResponse = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: both legs use the explicit expiry remedy code.
    expect(uploadResponse.status).toBe(410);
    expect(await uploadResponse.json()).toMatchObject({ code: "ticket_expired" });
    expect(completeResponse.status).toBe(410);
    expect(await completeResponse.json()).toMatchObject({ code: "ticket_expired" });
  });

  it("rejects oversized R2 objects before reading the body", async () => {
    // Given: R2 metadata says the object is above the server cap, and body reads would throw.
    const env = oversizeEnv();

    // When: finalization checks the uploaded object.
    const response = await handleFinalizeSubmission(
      jsonRequest(`/api/submissions/${RAW_BUNDLE_SHA}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
      }),
      env,
      { submissionId: "ticket_oversize" },
    );

    // Then: the route rejects from metadata without touching text().
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ code: "bundle_too_large" });
  });

  it("rejects a zip or binary body as an invalid bundle after hash verification", async () => {
    // Given: R2 contains non-JSON bytes at the content-addressed key.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const binary = new Uint8Array([80, 75, 3, 4, 0, 0, 0, 0]);
    const binarySha = await sha256Bytes(binary);
    const envelope = await issueEnvelope(env, binarySha);
    await env.SUBMISSIONS.put(rawBundleKey(binarySha), binary);

    // When: the complete route reads the object.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: binarySha,
        size_bytes: binary.byteLength,
      }),
    });

    // Then: binary uploads do not get parsed or accepted as result bundles.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_result_bundle" });
  });

  it("rejects community bundles containing dynamic benches", async () => {
    // Given: a community ticket targets the 5-axis release, but the uploaded bundle includes appworld_c.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const bundle = signedResultBundle(key.publicKeyHex, {
      items: [{ bench: "appworld_c", id: "dynamic-1" }],
    });
    const bundleJson = JSON.stringify(bundle);
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const envelope = await ticket.json();
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);

    // When: finalization enforces the origin-aware static-bench gate.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: the dynamic item is rejected, not stripped.
    expect(response.status).toBe(422);
    expect(await response.json()).toMatchObject({
      benches: ["appworld_c"],
      code: "dynamic_items_not_accepted",
    });
  });

  it("rejects key mismatch at complete", async () => {
    // Given: the ticket key differs from the signed bundle public key.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const ticketKey = testKeyPair();
    const bundleKey = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(bundleKey.publicKeyHex));
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, ticketKey), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const envelope = await ticket.json();
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);

    // When: finalization checks the signature public key binding.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: the ticket cannot be completed under a different key.
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ code: "key_mismatch" });
  });

  it("does not return another row for a cross-id complete probe", async () => {
    // Given: one raw bundle is already pending under its real submission id.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.DB.prepare("update submissions set status = 'pending_verification', uploaded_at = datetime('now') where submission_id = ?")
      .bind(envelope.ticket_id)
      .run();

    // When: a different path id probes that raw sha.
    const response = await completeSubmission({
      env,
      params: { submissionId: `probe_${envelope.ticket_id}` },
      request: jsonRequest(`/api/submissions/probe_${envelope.ticket_id}/complete`, {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: the route does not leak the existing row body.
    expect([404, 409]).toContain(response.status);
    expect(await response.json()).not.toMatchObject({ submission_id: envelope.ticket_id });
  });

  it("sets duplicate_of for the second key that submits the same canonical payload", async () => {
    // Given: two signed bundles differ only by their top-level signature public key.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const firstKey = testKeyPair();
    const secondKey = testKeyPair();
    const firstJson = JSON.stringify(signedResultBundle(firstKey.publicKeyHex));
    const secondJson = JSON.stringify(signedResultBundle(secondKey.publicKeyHex));
    const firstSha = sha256Hex(firstJson);
    const secondSha = sha256Hex(secondJson);
    const firstTicket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(firstSha, firstKey), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const firstEnvelope = await firstTicket.json();
    const secondTicket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(secondSha, secondKey), {
        "CF-Connecting-IP": "203.0.113.10",
      }),
    });
    const secondEnvelope = await secondTicket.json();
    await env.SUBMISSIONS.put(rawBundleKey(firstSha), firstJson);
    await env.SUBMISSIONS.put(rawBundleKey(secondSha), secondJson);

    // When: both bundles complete successfully.
    await completeSubmission({
      env,
      params: { submissionId: firstEnvelope.ticket_id },
      request: jsonRequest(`/api/submissions/${firstEnvelope.ticket_id}/complete`, {
        raw_bundle_sha256: firstSha,
        size_bytes: firstJson.length,
      }),
    });
    const secondResponse = await completeSubmission({
      env,
      params: { submissionId: secondEnvelope.ticket_id },
      request: jsonRequest(`/api/submissions/${secondEnvelope.ticket_id}/complete`, {
        raw_bundle_sha256: secondSha,
        size_bytes: secondJson.length,
      }),
    });

    // Then: the second row proceeds but is marked as a duplicate of the first.
    expect(secondResponse.status).toBe(200);
    expect(await secondResponse.json()).toMatchObject({
      duplicate_of: firstEnvelope.ticket_id,
      status: "pending_verification",
      submission_id: secondEnvelope.ticket_id,
    });
    const row = await env.DB.prepare("select duplicate_of from submissions where submission_id = ?")
      .bind(secondEnvelope.ticket_id)
      .first();
    expect(row).toMatchObject({ duplicate_of: firstEnvelope.ticket_id });
  });
});

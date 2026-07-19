import { describe, expect, it } from "vitest";
import { handleFinalizeSubmission } from "../functions/_lib/submission-api";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import {
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  completeProjection,
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
        upload_capability: envelope.upload_capability,
      }),
    });
    const completeResponse = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
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
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
      }),
      env,
      { submissionId: "ticket_oversize" },
    );

    // Then: the route rejects from metadata without touching text().
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ code: "bundle_too_large" });
  });

  it("admits content-addressed binary bytes for maintainer-side semantic rejection", async () => {
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
        accepted_result_projection: completeProjection(binarySha, "project_anchor"),
        raw_bundle_sha256: binarySha,
        size_bytes: binary.byteLength,
      }),
    });

    // Then: the Worker trusts the client projection without parsing or re-scoring the bundle.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
  });

  it("accepts community bundles containing dynamic benches with a community-origin row", async () => {
    // Given: a community ticket targets the 5-axis release and the uploaded bundle includes appworld_c.
    // (Owner decision 2026-07-04: community submissions carry all five axes; agentic verdicts are
    // labeled self-reported at rescore and rows only publish after manual admin acceptance.)
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const bundle = signedResultBundle(key);
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

    // When: the community submitter finalizes the upload.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "community"),
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: the complete dynamic projection publishes and origin stays server-derived.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      origin: "community",
      status: "published",
    });
  });

  it("does not require a bundle signature the shipped client does not produce", async () => {
    // Given: the ticket key differs from the signed bundle public key.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const ticketKey = testKeyPair();
    const bundleKey = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(bundleKey));
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, ticketKey), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const envelope = await ticket.json();
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);

    // When: finalization checks only the ticket-bound content address.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "community"),
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: ticket-time proof of possession remains the only admission signature check.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
  });

  it("defers bundle payload signature semantics to maintainer verification", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const bundle = signedResultBundle(key);
    bundle["run_finished_at"] = "2026-07-01T00:00:00Z";
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

    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "community"),
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
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
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    // Then: the route does not leak the existing row body.
    expect([404, 409]).toContain(response.status);
    expect(await response.json()).not.toMatchObject({ submission_id: envelope.ticket_id });
  });

  it("defers exact GGUF identity dedupe to maintainer verification", async () => {
    // Given: two signed bundles differ only by their top-level signature public key.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const firstKey = testKeyPair();
    const secondKey = testKeyPair();
    const firstJson = JSON.stringify(signedResultBundle(firstKey));
    const secondJson = JSON.stringify(signedResultBundle(secondKey));
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
        accepted_result_projection: completeProjection(firstSha, "community"),
        raw_bundle_sha256: firstSha,
        size_bytes: firstJson.length,
      }),
    });
    const secondResponse = await completeSubmission({
      env,
      params: { submissionId: secondEnvelope.ticket_id },
      request: jsonRequest(`/api/submissions/${secondEnvelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(secondSha, "community"),
        raw_bundle_sha256: secondSha,
        size_bytes: secondJson.length,
      }),
    });

    // Then: both distinct content-addressed runs publish without server re-scoring.
    expect(secondResponse.status).toBe(200);
    expect(await secondResponse.json()).toMatchObject({ status: "published" });
    const row = await env.DB.prepare("select duplicate_of, model_identity_digest from submissions where submission_id = ?")
      .bind(secondEnvelope.ticket_id)
      .first();
    expect(row).toMatchObject({ duplicate_of: null, model_identity_digest: "a".repeat(64) });
  }, 15_000);

  it("does not impose the deleted pending-review cap on pre-minted tickets", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const pending: Array<{ bundleJson: string; bundleSha: string; ticketId: string }> = [];
    for (let index = 0; index < 11; index += 1) {
      const modelSha = index.toString(16).padStart(64, "0");
      const bundleJson = JSON.stringify(signedResultBundle(key, {}, modelSha));
      const bundleSha = sha256Hex(bundleJson);
      const ticket = await issueTicket({
        env,
        request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
          "CF-Connecting-IP": TEST_IP,
        }),
      });
      const envelope = await ticket.json();
      await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
      pending.push({ bundleJson, bundleSha, ticketId: envelope.ticket_id });
    }

    const responses: Response[] = [];
    for (const item of pending) {
      responses.push(await completeSubmission({
        env,
        params: { submissionId: item.ticketId },
        request: jsonRequest(`/api/submissions/${item.ticketId}/complete`, {
          accepted_result_projection: completeProjection(item.bundleSha, "community"),
          raw_bundle_sha256: item.bundleSha,
          size_bytes: item.bundleJson.length,
        }),
      }));
    }

    expect(responses.every((response) => response.status === 200)).toBe(true);
    expect(await responses[10]?.json()).toMatchObject({ status: "published" });
  }, 60_000);

  it("publishes while legacy pending rows remain readable", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    await env.DB.prepare(
      `with recursive n(x) as (select 1 union all select x + 1 from n where x < 200)
       insert into submissions (
         submission_id, origin, submitter_id, ticket_id, status, raw_bundle_sha256,
         idempotency_key, publish_state, uploaded_at, model_identity_digest
       ) select 'pending_' || x, 'community', 'public_key:' || printf('%064x', x),
         'pending_' || x, 'pending_verification', printf('%064x', x), printf('%064x', x),
         'hidden', datetime('now'), printf('%064x', x) from n`,
    ).run();
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(rawBundleKey(RAW_BUNDLE_SHA), RESULT_BUNDLE_JSON);

    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: RESULT_BUNDLE_JSON.length,
      }),
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
  }, 15_000);
});

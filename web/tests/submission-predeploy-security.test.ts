import { describe, expect, it } from "vitest";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestGet as listSubmissions } from "../functions/api/submissions/list";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { MAX_UPLOAD_BYTES } from "../functions/_lib/submission-contracts";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import {
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  completeProjection,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
} from "./submission-test-support";
import { TEST_IP, communityTicketBody, testKeyPair } from "./submission-contract-v2-support";

describe("submission pre-deploy security regressions", () => {
  it.each([
    ["missing", undefined],
    ["wrong", `upload_${"f".repeat(32)}`],
  ])("rejects a %s completion capability without mutating the ticket or object", async (_label, capability) => {
    // Given: a live ticket and its content-addressed raw object.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(rawBundleKey(RAW_BUNDLE_SHA), RESULT_BUNDLE_JSON);
    const body = {
      accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      size_bytes: RESULT_BUNDLE_JSON.length,
      ...(capability === undefined ? {} : { upload_capability: capability }),
    };

    // When: a caller without the issued capability attempts completion.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, body),
    });

    // Then: neither D1 submission state, its rate budget, nor the R2 object changes.
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ code: "upload_capability_invalid" });
    const row = await env.DB.prepare("select status, uploaded_at from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "ticketed", uploaded_at: null });
    const counter = await env.DB.prepare("select count from rate_counters where bucket_key = ?")
      .bind(`complete:submission:${envelope.ticket_id}`)
      .first();
    expect(counter).toBeNull();
    expect(await env.SUBMISSIONS.get(rawBundleKey(RAW_BUNDLE_SHA))).not.toBeNull();
  });

  it("rejects a completion body declared above the application cap before mutation", async () => {
    // Given: a valid ticket, capability, and raw object, but an oversized HTTP body declaration.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(rawBundleKey(RAW_BUNDLE_SHA), RESULT_BUNDLE_JSON);
    const request = jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
      accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      upload_capability: envelope.upload_capability,
    }, { "content-length": String(512 * 1024 + 1) });

    // When: completion receives the request.
    const response = await completeSubmission({ env, params: { submissionId: envelope.ticket_id }, request });

    // Then: the application rejects before projection parsing, R2 access, or state transition.
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ code: "completion_body_too_large" });
    const row = await env.DB.prepare("select status from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "ticketed" });
    expect(await env.SUBMISSIONS.get(rawBundleKey(RAW_BUNDLE_SHA))).not.toBeNull();
  });

  it("issues one exact-length upload target and charges its byte budget once", async () => {
    // Given: a live ticket and a declared raw-object size.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const body = {
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      size_bytes: RESULT_BUNDLE_JSON.length,
      ticket_id: envelope.ticket_id,
      upload_capability: envelope.upload_capability,
    };

    // When: the client repeats upload-target issuance for the same ticket.
    const first = await requestUpload({ env, request: jsonRequest("/api/submissions/request-upload", body) });
    const second = await requestUpload({ env, request: jsonRequest("/api/submissions/request-upload", body) });

    // Then: the signed target is stable, binds Content-Length, and consumes one byte charge.
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    const firstTarget = await first.json();
    const secondTarget = await second.json();
    expect(secondTarget).toEqual(firstTarget);
    expect(firstTarget.upload_headers).toMatchObject({
      "content-length": String(RESULT_BUNDLE_JSON.length),
      "if-none-match": "*",
    });
    const day = new Date().toISOString().slice(0, 10);
    const counter = await env.DB.prepare("select count from rate_counters where bucket_key = ?")
      .bind(`upload_bytes:${day}`)
      .first();
    expect(counter).toMatchObject({ count: RESULT_BUNDLE_JSON.length });
  });

  it("does not charge replayed upload-target requests rejected by the daily budget", async () => {
    // Given: a live ticket after the daily upload-byte budget is exhausted.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const nowSeconds = Math.floor(Date.now() / 1000);
    const windowStartSeconds = nowSeconds - (nowSeconds % (24 * 60 * 60));
    const day = new Date().toISOString().slice(0, 10);
    const budgetKey = `upload_bytes:${day}`;
    const dailyBudget = 8 * 1024 * 1024 * 1024;
    await env.DB.prepare(
      "insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)",
    ).bind(budgetKey, new Date(windowStartSeconds * 1000).toISOString(), dailyBudget).run();
    const body = {
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      size_bytes: RESULT_BUNDLE_JSON.length,
      ticket_id: envelope.ticket_id,
      upload_capability: envelope.upload_capability,
    };

    // When: the client repeats the same over-budget upload-target request.
    const first = await requestUpload({ env, request: jsonRequest("/api/submissions/request-upload", body) });
    const second = await requestUpload({ env, request: jsonRequest("/api/submissions/request-upload", body) });

    // Then: both requests are rejected without increasing the persisted daily charge.
    expect(first.status).toBe(429);
    expect(second.status).toBe(429);
    expect(await first.json()).toMatchObject({ code: "upload_byte_budget_exceeded" });
    expect(await second.json()).toMatchObject({ code: "upload_byte_budget_exceeded" });
    const counter = await env.DB.prepare("select count from rate_counters where bucket_key = ?")
      .bind(budgetKey)
      .first();
    expect(counter).toMatchObject({ count: dailyBudget });
  });

  it("rejects an oversized upload declaration without charging a one-byte budget", async () => {
    // Given: a live ticket and an upload request above the hard object cap.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);

    // When: the client requests a target for an oversized object.
    const response = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: MAX_UPLOAD_BYTES + 1,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
      }),
    });

    // Then: validation rejects before either a target or byte-budget charge is issued.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_upload_target_request" });
    const day = new Date().toISOString().slice(0, 10);
    const counter = await env.DB.prepare("select count from rate_counters where bucket_key = ?")
      .bind(`upload_bytes:${day}`)
      .first();
    expect(counter).toBeNull();
  });

  it("deletes and rejects an object whose actual size differs from the signed declaration", async () => {
    // Given: a target signed for one byte, followed by a directly injected larger R2 object.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const target = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: 1,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
      }),
    });
    expect(target.status).toBe(200);
    await env.SUBMISSIONS.put(rawBundleKey(RAW_BUNDLE_SHA), RESULT_BUNDLE_JSON);

    // When: the ticket holder attempts completion with the mismatched object.
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        upload_capability: envelope.upload_capability,
      }),
    });

    // Then: the oversized-for-target object is deleted and the rejection is GC-timestamped.
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ code: "upload_size_mismatch" });
    expect(await env.SUBMISSIONS.get(rawBundleKey(RAW_BUNDLE_SHA))).toBeNull();
    const row = await env.DB.prepare("select status, validated_at from submissions where submission_id = ?")
      .bind(envelope.ticket_id)
      .first();
    expect(row).toMatchObject({ status: "rejected" });
    expect(row?.["validated_at"]).toEqual(expect.any(String));
  });

  it("omits ticketed and rejected submission ids from the unauthenticated list", async () => {
    // Given: private ticketed/rejected rows and one public published row.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const rows = [
      { id: "private_ticketed", publishState: "hidden", status: "ticketed" },
      { id: "private_rejected", publishState: "hidden", status: "rejected" },
      { id: "public_published", publishState: "published", status: "published" },
    ] as const;
    for (const [index, row] of rows.entries()) {
      const sha = index.toString(16).padStart(64, "0");
      await env.DB.prepare(
        `insert into submissions (
          submission_id, origin, status, raw_bundle_sha256, idempotency_key, publish_state,
          published_at, validated_at
        ) values (?, 'community', ?, ?, ?, ?, ?, ?)`,
      ).bind(
        row.id,
        row.status,
        sha,
        sha,
        row.publishState,
        row.status === "published" ? "2026-07-19 00:00:00" : null,
        row.status === "published" ? "2026-07-19 00:00:00" : null,
      ).run();
    }

    // When: an unauthenticated caller lists submissions.
    const response = await listSubmissions({ env, request: getRequest("/api/submissions/list") });

    // Then: only the public state is enumerable.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.submissions.map((row: { readonly submission_id: string }) => row.submission_id))
      .toEqual(["public_published"]);
  });

  it("returns the same usable envelope to concurrent identical ticket requests", async () => {
    // Given: two byte-identical, PoP-valid ticket requests race on an unseen raw hash.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key);

    // When: both requests enter ticket issuance concurrently.
    const responses = await Promise.all([
      issueTicket({
        env,
        request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
      }),
      issueTicket({
        env,
        request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
      }),
    ]);

    // Then: both succeed with the single persisted envelope and capability.
    expect(responses.every((response) => response.status === 200 || response.status === 201)).toBe(true);
    const envelopes = await Promise.all(responses.map((response) => response.json()));
    expect(envelopes[1]).toEqual(envelopes[0]);
    const count = await env.DB.prepare("select count(*) as count from submissions where raw_bundle_sha256 = ?")
      .bind(RAW_BUNDLE_SHA)
      .first();
    expect(count).toMatchObject({ count: 1 });
  });
});

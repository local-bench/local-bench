import { describe, expect, it } from "vitest";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import {
  ADMIN_SECRET,
  RAW_BUNDLE_SHA,
  createEnv,
  jsonRequest,
  ticketRequest,
} from "./submission-test-support";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import {
  FIVE_AXIS_SUITE_MANIFEST_SHA,
  FIVE_AXIS_SUITE_RELEASE_ID,
  TEST_IP,
  communityTicketBody,
  testKeyPair,
} from "./submission-contract-v2-support";

describe("submission contract v2 ticket route", () => {
  it("rejects a community ticket without an explicit suite release pair", async () => {
    // Given: an anonymous submitter proves key possession but omits the required suite pair.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key, {
      expected_suite_manifest_sha256: undefined,
      expected_suite_release_id: undefined,
    });

    // When: the public ticket route is called without an admin secret.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
    });

    // Then: community requests do not receive admin defaults.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_ticket_request" });
  });

  it("rejects a community ticket with an unregistered suite release pair", async () => {
    // Given: the submitter names a release/manifest pair outside the server catalog.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key, {
      expected_suite_manifest_sha256: "c".repeat(64),
      expected_suite_release_id: "suite-v1-unknown",
    });

    // When: the public ticket route validates the request.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
    });

    // Then: unknown registered-pair claims are typed rejections.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "unknown_suite_release" });
  });

  it("rejects a body-supplied origin on any ticket request", async () => {
    // Given: an admin caller tries to supply the trust origin in the request body.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });

    // When: the ticket route receives the trust field.
    const response = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        ticketRequest(RAW_BUNDLE_SHA, { origin: "project_anchor" }),
        { "x-localbench-admin-secret": ADMIN_SECRET },
      ),
    });

    // Then: origin remains server-derived only.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_ticket_request" });
  });

  it("rejects declared model labels that are not catalog slugs", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", ticketRequest(RAW_BUNDLE_SHA, {
        declared_model_slug: "Vendor / Fake Model",
      }), {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_ticket_request" });
  });

  it("rejects a community ticket with missing proof of possession", async () => {
    // Given: a public-key submitter omits the required PoP object.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key, { pop: undefined });

    // When: the public ticket route validates the request.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
    });

    // Then: missing PoP is a typed PoP failure, not a generic schema leak.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "pop_invalid" });
  });

  it("rejects a community ticket with an invalid proof-of-possession signature", async () => {
    // Given: the PoP timestamp is fresh but the signature is not over the canonical string.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key, {
      pop: { signature: "0".repeat(128), timestamp: new Date().toISOString() },
    });

    // When: the public ticket route verifies PoP.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
    });

    // Then: bad signatures are rejected before ticket minting.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "pop_invalid" });
  });

  it("rejects a community ticket with a stale proof-of-possession timestamp", async () => {
    // Given: the PoP signature is valid but outside the ten-minute window.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const timestamp = new Date(Date.now() - 11 * 60 * 1000).toISOString();
    const body = communityTicketBody(RAW_BUNDLE_SHA, key, { timestamp });

    // When: the public ticket route checks the freshness window.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", body, { "CF-Connecting-IP": TEST_IP }),
    });

    // Then: stale but otherwise valid signatures receive the stale code.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "pop_stale" });
  });

  it("rejects a free-text submitter_id on the public path", async () => {
    // Given: a non-admin caller tries to squat a submitter id.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });

    // When: the request lacks a valid admin secret.
    const response = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        ticketRequest(RAW_BUNDLE_SHA, {
          expected_suite_manifest_sha256: FIVE_AXIS_SUITE_MANIFEST_SHA,
          expected_suite_release_id: FIVE_AXIS_SUITE_RELEASE_ID,
        }),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });

    // Then: public identity is derived only from public_key.
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "invalid_ticket_request" });
  });

  it("keeps the admin path project-anchor with suite defaults", async () => {
    // Given: an admin request uses the legacy free-text submitter id and no explicit pair.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });

    // When: the ticket route sees a valid admin secret.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", ticketRequest(), {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: admin tooling still mints project-anchor envelopes with v2 defaults.
    expect(response.status).toBe(201);
    expect(await response.json()).toMatchObject({
      expected_suite_manifest_sha256: FIVE_AXIS_SUITE_MANIFEST_SHA,
      expected_suite_release_id: FIVE_AXIS_SUITE_RELEASE_ID,
      origin: "project_anchor",
      schema_version: "localbench.submission_envelope.v2",
      submitter_id: "project-anchor",
    });
  });

  it("carries an optional submitter display name for board credit", async () => {
    // Given: a community submitter wants visible credit next to their row.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();

    // When: the ticket names a display name, then a re-mint renames it, then a bad name tries.
    const first = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        communityTicketBody(RAW_BUNDLE_SHA, key, { submitter_display_name: "Quant Cowboy" }),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });
    const firstBody = await first.json();
    const rotated = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        communityTicketBody(RAW_BUNDLE_SHA, key, { submitter_display_name: "Quant.Cowboy_2" }),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });
    const invalid = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        communityTicketBody("d".repeat(64), key, { submitter_display_name: "https://spam.example/x" }),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });

    // Then: the name is echoed, stored, updated on rotation, and URL-shaped names are rejected.
    expect(first.status).toBe(201);
    expect(firstBody.submitter_display_name).toBe("Quant Cowboy");
    expect(rotated.status).toBe(200);
    const stored = await env.DB.prepare("select submitter_display_name from submissions where raw_bundle_sha256 = ?")
      .bind(RAW_BUNDLE_SHA)
      .first();
    expect(stored?.["submitter_display_name"]).toBe("Quant.Cowboy_2");
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toMatchObject({ code: "invalid_ticket_request" });
  });

  it("rotates a live same-submitter ticket and conflicts on submitted or different-submitter rows", async () => {
    // Given: a community submitter has one live ticket for a raw bundle.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const first = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(RAW_BUNDLE_SHA, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const firstBody = await first.json();

    // When: the same submitter remints before upload.
    const rotated = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(RAW_BUNDLE_SHA, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });

    // Then: the ticket rotates in place.
    expect(first.status).toBe(201);
    expect(rotated.status).toBe(200);
    const rotatedBody = await rotated.json();
    expect(rotatedBody.ticket_id).not.toBe(firstBody.ticket_id);
    expect(rotatedBody.bundle_sha256).toBe(RAW_BUNDLE_SHA);

    // Then: the rotated ticket id reaches the upload leg, and the stale one is dead.
    // (Pins the rotation model: submission_id and ticket_id move in lockstep, so the
    // upload leg's submission-id lookup keeps working after any number of re-mints.)
    const rotatedUpload = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: rotatedBody.ticket_id,
        upload_capability: rotatedBody.upload_capability,
      }),
    });
    expect(rotatedUpload.status).toBe(200);
    const staleUpload = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        ticket_id: firstBody.ticket_id,
        upload_capability: firstBody.upload_capability,
      }),
    });
    expect(staleUpload.status).toBe(404);
    expect(await staleUpload.json()).toMatchObject({ code: "unknown_ticket" });

    // When: another key tries the same bundle, and when the bundle has already uploaded.
    const otherKey = testKeyPair();
    const otherSubmitter = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(RAW_BUNDLE_SHA, otherKey), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    await env.DB.prepare("update submissions set status = 'pending_verification', uploaded_at = datetime('now') where raw_bundle_sha256 = ?")
      .bind(RAW_BUNDLE_SHA)
      .run();
    const sameAfterUpload = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(RAW_BUNDLE_SHA, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });

    // Then: both cases are conflicts without an envelope.
    expect(otherSubmitter.status).toBe(409);
    expect(await otherSubmitter.json()).toMatchObject({ code: "bundle_already_submitted" });
    expect(sameAfterUpload.status).toBe(409);
    expect(await sameAfterUpload.json()).toMatchObject({ code: "bundle_already_submitted" });
  }, 15_000);

  it("rate-limits community ticket mints after the launch limit", async () => {
    // Given: one public key mints fresh tickets under the same fixed daily bucket.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const responses: Response[] = [];

    // When: the submitter exceeds twenty ticket mints (the per-key daily cap).
    for (let index = 0; index < 21; index += 1) {
      const bundleSha = `${index.toString(16).padStart(63, "0")}a`;
      responses.push(await issueTicket({
        env,
        request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
          "CF-Connecting-IP": TEST_IP,
        }),
      }));
    }

    // Then: the twenty-first request is rejected with retry guidance.
    expect(responses.slice(0, 20).every((response) => response.status === 201)).toBe(true);
    expect(responses[20]?.status).toBe(429);
    expect(await responses[20]?.json()).toMatchObject({ code: "rate_limited" });
  }, 30_000);

  it("caps tickets behind the pending-review limit with an honest non-timer rejection", async () => {
    // Given: one public key already has five submissions sitting in pending_verification.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    for (let index = 0; index < 5; index += 1) {
      const bundleSha = `${index.toString(16).padStart(63, "0")}b`;
      const minted = await issueTicket({
        env,
        request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
          "CF-Connecting-IP": TEST_IP,
        }),
      });
      expect(minted.status).toBe(201);
      await env.DB.prepare(
        "update submissions set status = 'pending_verification', uploaded_at = datetime('now') where raw_bundle_sha256 = ?",
      )
        .bind(bundleSha)
        .run();
    }

    // When: the same key asks for a sixth ticket.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(`${"5".padStart(63, "0")}b`, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });

    // Then: rejected with the review-gated code, not a misleading retry_after timer.
    expect(response.status).toBe(429);
    const body = await response.json();
    expect(body).toMatchObject({ code: "pending_review_limit", pending_limit: 5 });
    expect(body).not.toHaveProperty("retry_after_seconds");
  }, 30_000);

  it("rate-limits community ticket mints after the IPv4 prefix daily cap", async () => {
    // Given: the caller's /24 prefix bucket is already at the daily admission cap.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    await seedRateCounter(env, {
      bucketKey: "tickets:ipprefix:203.0.113.0/24",
      count: 60,
      windowSeconds: 24 * 60 * 60,
    });

    // When: a fresh key from that prefix asks for another ticket.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody("9".repeat(64), key), {
        "CF-Connecting-IP": "203.0.113.99",
      }),
    });

    // Then: the prefix-level cap rejects before minting a Sybil-cheap ticket.
    expect(response.status).toBe(429);
    expect(await response.json()).toMatchObject({ code: "rate_limited" });
  });

  it("rate-limits community ticket mints after the global daily cap", async () => {
    // Given: the global daily ticket bucket is already at the launch cap.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    await seedRateCounter(env, {
      bucketKey: "tickets:global:day",
      count: 400,
      windowSeconds: 24 * 60 * 60,
    });

    // When: a valid community request arrives from an otherwise clean IP and key.
    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody("8".repeat(64), key), {
        "CF-Connecting-IP": "198.51.100.10",
      }),
    });

    // Then: admission control rejects the request with the standard 429 shape.
    expect(response.status).toBe(429);
    expect(await response.json()).toMatchObject({ code: "rate_limited" });
  });
});

async function seedRateCounter(
  env: SubmissionApiEnv,
  counter: { readonly bucketKey: string; readonly count: number; readonly windowSeconds: number },
): Promise<void> {
  await env.DB.prepare("insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)")
    .bind(counter.bucketKey, rateLimitWindowStart(counter.windowSeconds), counter.count)
    .run();
}

function rateLimitWindowStart(windowSeconds: number): string {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % windowSeconds);
  return new Date(windowStartSeconds * 1000).toISOString();
}

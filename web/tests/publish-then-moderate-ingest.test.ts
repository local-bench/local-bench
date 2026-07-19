import { describe, expect, it } from "vitest";
import { handleCreateCommunityModelGroup } from "../functions/_lib/community-model-groups";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as runGc } from "../functions/api/admin/gc";
import {
  ADMIN_SECRET,
  RAW_BUNDLE_SHA,
  completeProjection,
  createEnv,
  issueEnvelope,
  jsonRequest,
} from "./submission-test-support";
import { communityGroupBody, testKeyPair } from "./submission-contract-v2-support";

const GIB = 1024 * 1024 * 1024;

describe("publish-then-moderate ingest budgets", () => {
  it("rate-limits community model-group creation to ten per IP per day", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const statuses: number[] = [];
    for (let index = 0; index < 11; index += 1) {
      const response = await handleCreateCommunityModelGroup(jsonRequest(
        "/api/community-model-groups",
        communityGroupBody(`Fixture group ${index}`, key),
        { "CF-Connecting-IP": "192.0.2.10" },
      ), env);
      statuses.push(response.status);
    }
    expect(statuses.slice(0, 10)).toEqual(Array.from({ length: 10 }, () => 201));
    expect(statuses[10]).toBe(429);
  });

  it("deletes the uploaded R2 object after a byte-digest failure", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const mismatchedBytes = "synthetic mismatched bytes";
    const envelope = await issueEnvelope(env, RAW_BUNDLE_SHA, {}, mismatchedBytes.length);
    const key = `submissions/raw/${RAW_BUNDLE_SHA}.json`;
    await env.SUBMISSIONS.put(key, mismatchedBytes);
    const response = await completeSubmission({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/submissions/${envelope.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(RAW_BUNDLE_SHA, "project_anchor"),
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        upload_capability: envelope.upload_capability,
      }),
    });
    expect(response.status).toBe(400);
    expect(await env.SUBMISSIONS.get(key)).toBeNull();
  });

  it("refuses upload grants beyond the eight-GiB daily byte budget", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const nowSeconds = Math.floor(Date.now() / 1000);
    const windowStartSeconds = nowSeconds - (nowSeconds % (24 * 60 * 60));
    const day = new Date().toISOString().slice(0, 10);
    await env.DB.prepare(
      "insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)",
    ).bind(`upload_bytes:${day}`, new Date(windowStartSeconds * 1000).toISOString(), 8 * GIB).run();

    const response = await requestUpload({
      env,
      request: jsonRequest("/api/submissions/request-upload", {
        raw_bundle_sha256: RAW_BUNDLE_SHA,
        size_bytes: 1024,
        ticket_id: envelope.ticket_id,
        upload_capability: envelope.upload_capability,
      }),
    });
    expect(response.status).toBe(429);
    expect(await response.json()).toMatchObject({ code: "upload_byte_budget_exceeded" });
  });

  it("deletes rejected raw bundles after seven days", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const rawSha = "f".repeat(64);
    const key = `submissions/raw/${rawSha}.json`;
    await env.SUBMISSIONS.put(key, "synthetic rejected fixture");
    await env.DB.prepare(
      `insert into submissions (
        submission_id, origin, status, raw_bundle_sha256, raw_bundle_r2_key,
        idempotency_key, publish_state, validated_at
      ) values ('ticket_fixture_gc_rejected', 'community', 'rejected', ?, ?, ?, 'hidden', datetime('now', '-8 days'))`,
    ).bind(rawSha, key, rawSha).run();

    const response = await runGc({
      env,
      request: jsonRequest("/api/admin/gc", { apply: true }, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });
    expect(response.status).toBe(200);
    expect(await env.SUBMISSIONS.get(key)).toBeNull();
  });

  it("retains a rejected raw bundle while a non-terminal row shares its digest", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const rawSha = "e".repeat(64);
    const key = `submissions/raw/${rawSha}.json`;
    await env.SUBMISSIONS.put(key, "synthetic shared-digest fixture");
    await env.DB.prepare("drop index submissions_raw_bundle_sha256_uq").run();
    await env.DB.prepare("pragma ignore_check_constraints = on").run();
    await env.DB.prepare(
      `insert into submissions (
        submission_id, origin, status, raw_bundle_sha256, raw_bundle_r2_key,
        idempotency_key, publish_state, validated_at
      ) values
        ('ticket_fixture_gc_shared_rejected', 'community', 'rejected', ?, ?, ?, 'hidden', datetime('now', '-8 days')),
        ('ticket_fixture_gc_shared_pending', 'community', 'pending_verification', ?, ?, ?, 'hidden', null)`,
    ).bind(rawSha, key, "c".repeat(64), rawSha, key, "d".repeat(64)).run();

    await runGc({
      env,
      request: jsonRequest("/api/admin/gc", { apply: true }, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    expect(await env.SUBMISSIONS.get(key)).not.toBeNull();
  });
});

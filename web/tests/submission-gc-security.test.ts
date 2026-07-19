import { describe, expect, it } from "vitest";
import { onRequestPost as gcSubmissions } from "../functions/api/admin/gc";
import { ADMIN_SECRET, createEnv, jsonRequest } from "./submission-test-support";

describe("submission GC publication retention", () => {
  it("includes published raw bundles after the retention window", async () => {
    // Given: a publish-on-submit row whose raw bundle is older than ninety days.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const rawSha = "9".repeat(64);
    await env.DB.prepare(
      `insert into submissions (
        submission_id, origin, status, raw_bundle_sha256, raw_bundle_r2_key,
        idempotency_key, publish_state, uploaded_at, validated_at, published_at
      ) values (
        'published-old', 'community', 'published', ?, 'submissions/raw/published-old.json',
        ?, 'published', '2000-01-01 00:00:00', '2000-01-01 00:00:00', '2000-01-01 00:00:00'
      )`,
    ).bind(rawSha, rawSha).run();

    // When: an administrator previews garbage collection.
    const response = await gcSubmissions({
      env,
      request: jsonRequest("/api/admin/gc", { apply: false }, { "x-localbench-admin-secret": ADMIN_SECRET }),
    });

    // Then: the published raw object is selected by the accepted retention bucket.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      accepted_raw_deleted: { count: 1, submission_ids: ["published-old"] },
    });
  });
});

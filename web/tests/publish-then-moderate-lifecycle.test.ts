import { describe, expect, it } from "vitest";
import { onRequestGet as listLifecycle } from "../functions/api/submissions/list";
import {
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0006,
  MIGRATION_0008,
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  MIGRATION_0013,
  MIGRATION_0014,
  createEnv,
  getRequest,
} from "./submission-test-support";

describe("public submission lifecycle listing", () => {
  it("paginates every lifecycle state with a sanitized keyset cursor", async () => {
    const env = await lifecycleEnv();
    for (let index = 0; index < 55; index += 1) {
      const id = `ticket_fixture_lifecycle_${String(index).padStart(2, "0")}`;
      const status = index === 0 ? "rejected" : index === 1 ? "accepted" : "pending_verification";
      await env.DB.prepare(
        `insert into submissions (
          submission_id, origin, submitter_id, submitter_display_name, declared_model_slug,
          status, status_reason, raw_bundle_sha256, idempotency_key, publish_state,
          published_at, validated_at, created_at, zt1_decision
        ) values (?, 'community', ?, 'Fixture Submitter', 'fixture-model', ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).bind(
        id,
        `public_key:${index.toString(16).padStart(64, "0")}`,
        status,
        status === "rejected" ? "schema_violation" : null,
        index.toString(16).padStart(64, "0"),
        index.toString(16).padStart(64, "0"),
        status === "accepted" ? "published" : "hidden",
        status === "accepted" ? "2026-07-18 00:00:00" : null,
        status === "pending_verification" ? null : "2026-07-18 00:00:00",
        `2026-07-17 00:${String(index).padStart(2, "0")}:00`,
        index === 1 ? "escalated" : null,
      ).run();
    }

    const first = await listLifecycle({ env, request: getRequest("/api/submissions/list") });
    const firstBody = await first.json();
    const second = await listLifecycle({
      env,
      request: getRequest(`/api/submissions/list?cursor=${encodeURIComponent(String(firstBody.next_cursor))}`),
    });
    const secondBody = await second.json();
    const serialized = JSON.stringify([firstBody, secondBody]);

    expect(first.status).toBe(200);
    expect(first.headers.get("cache-control")).toBe("public, max-age=0, s-maxage=60");
    expect(firstBody.submissions).toHaveLength(50);
    expect(secondBody.submissions).toHaveLength(5);
    expect(new Set([...firstBody.submissions, ...secondBody.submissions]
      .map((row: { submission_id: string }) => row.submission_id)).size).toBe(55);
    expect(serialized).not.toMatch(/r2_key|zt1_|capability|admin|upload_/i);
    const legacyEscalated = [...firstBody.submissions, ...secondBody.submissions]
      .find((row: { submission_id: string }) => row.submission_id === "ticket_fixture_lifecycle_01");
    expect(legacyEscalated).toMatchObject({ publish_state: "published", status: "accepted" });
    expect(legacyEscalated).not.toHaveProperty("held_for_review");
    const rejected = [...firstBody.submissions, ...secondBody.submissions]
      .find((row: { submission_id: string }) => row.submission_id === "ticket_fixture_lifecycle_00");
    expect(rejected).toMatchObject({ reason_code: "schema_violation", status: "rejected" });
  });

  it("rejects malformed cursors", async () => {
    const env = await lifecycleEnv();
    const response = await listLifecycle({ env, request: getRequest("/api/submissions/list?cursor=not-a-cursor") });
    expect(response.status).toBe(400);
  });
});

function lifecycleEnv() {
  return createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
      MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014,
    ],
  });
}

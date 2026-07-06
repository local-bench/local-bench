import { describe, expect, it } from "vitest";
import { onRequestGet as acceptedFeed } from "../functions/api/feed/accepted.json";
import { onRequestGet as statusRoute } from "../functions/api/submissions/[submissionId]";
import { acceptedSubmission, createZt0Env, insertSubmission, RAW_BUNDLE_SHA } from "./submission-zt0-support";

describe("ZT-0 public visibility", () => {
  it("serves a sanitized accepted feed with public caching", async () => {
    // Given: accepted and rejected submissions exist with private submitter ids.
    const env = await createZt0Env();
    const older = await acceptedSubmission(env, {
      publishState: "preview",
      rawSha: `${"4".repeat(64)}`,
      submitterDisplayName: "Older Runner",
      validatedAt: "2026-01-01T00:00:00Z",
    });
    const newer = await acceptedSubmission(env, {
      publishState: "published",
      rawSha: `${"5".repeat(64)}`,
      submitterDisplayName: "New Runner",
      validatedAt: "2026-01-02T00:00:00Z",
    });
    await insertSubmission(env, { id: "rejected-feed", rawSha: `${"6".repeat(64)}`, status: "rejected" });

    // When: the accepted feed is requested.
    const response = await acceptedFeed({ env });

    // Then: only accepted rows appear, newest first, without private fields.
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("public, max-age=300");
    const body = await response.json();
    expect(body).toEqual({
      submissions: [
        expect.objectContaining({ submission_id: newer, submitter_display_name: "New Runner" }),
        expect.objectContaining({ submission_id: older, submitter_display_name: "Older Runner" }),
      ],
    });
    expect(JSON.stringify(body)).not.toContain("submitter_id");
    expect(JSON.stringify(body)).not.toContain("status_reason");
  });

  it("adds public status history without exposing non-rejection reasons", async () => {
    // Given: a rejected row has transition history with both public and private reasons.
    const env = await createZt0Env();
    await insertSubmission(env, {
      id: "status-history",
      rawSha: RAW_BUNDLE_SHA,
      status: "rejected",
      statusReason: "schema mismatch",
    });
    await env.DB.prepare(
      `insert into submission_transitions
        (submission_id, from_status, to_status, publish_state, actor, reason, created_at)
       values (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        "status-history",
        "ticketed",
        "pending_verification",
        "hidden",
        "system",
        "private upload detail",
        "2026-01-01T00:00:00Z",
        "status-history",
        "pending_verification",
        "rejected",
        "hidden",
        "maintainer",
        "schema mismatch",
        "2026-01-02T00:00:00Z",
      )
      .run();

    // When: the public status endpoint is requested.
    const response = await statusRoute({ env, params: { submissionId: "status-history" } });

    // Then: history is additive and only rejected exposes the reason.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      status: "rejected",
      status_reason: "schema mismatch",
      suite_release_id: "suite-v1-text-code-agentic-5axis-v1",
    });
    expect(body.history).toEqual([
      { actor: "system", created_at: "2026-01-01T00:00:00Z", to_status: "pending_verification" },
      {
        actor: "maintainer",
        created_at: "2026-01-02T00:00:00Z",
        reason: "schema mismatch",
        to_status: "rejected",
      },
    ]);
  });
});

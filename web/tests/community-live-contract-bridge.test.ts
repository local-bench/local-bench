import { describe, expect, it } from "vitest";
import { LiveBoardEnvelopeSchema, LiveBoardRowSchema } from "../lib/community-live-schema";
import { parseSubmissionLifecyclePage } from "../lib/submission-lifecycle";
import { onRequestGet as listLifecycle } from "../functions/api/submissions/list";
import { RAW_BUNDLE_SHA, RESULT_BUNDLE_JSON, getRequest, statusUpdate } from "./submission-test-support";
import { insertPendingFixture, ptmEnv, storedBoard, verifyUpdate } from "./publish-then-moderate-test-support";

// Cross-track contract bridge: Track A's REAL pipeline output (verification POST
// -> auto-publish -> materialized board object) must parse byte-for-byte under
// Track B's strict client schemas. Both sides were built independently against
// design doc s6/s12; this test is the seam's regression lock.
const BRIDGE_SUBMISSION_ID = `ticket_${"a".repeat(32)}`;

describe("community live board contract bridge (Track A output vs Track B parser)", () => {
  it("materialized board from a real auto-published verification parses under the client schemas", async () => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, {
      rawJson: RESULT_BUNDLE_JSON,
      rawSha: RAW_BUNDLE_SHA,
      submissionId: BRIDGE_SUBMISSION_ID,
    });

    const response = await verifyUpdate(env, {
      submissionId: BRIDGE_SUBMISSION_ID,
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    expect(response.status).toBe(200);

    const board = await storedBoard(env);
    expect(board).not.toBeNull();

    const envelope = LiveBoardEnvelopeSchema.parse(board);
    expect(envelope.schema_version).toBe("localbench.community_live_board.v1");
    expect(envelope.rows.length).toBe(1);
    expect(envelope.omitted_rows).toBe(0);

    const row = LiveBoardRowSchema.parse(envelope.rows[0]);
    expect(row.submission_id).toBe(BRIDGE_SUBMISSION_ID);
    expect(row.origin).toBe("community");
    expect(row.badge).toBeUndefined();
    expect(row.trust).toBeUndefined();
    expect(row.submitter.unverified_handle).toBe("Fixture Submitter");
    expect(row.community_model_group_id).toBeDefined();
    expect(row.group_path).toBe(
      `community/groups/${row.community_model_group_id?.replace("community-group:", "")}.json`,
    );
  });

  it("lifecycle listing from the real endpoint parses under the client lifecycle schema", async () => {
    const env = await ptmEnv(true);
    const states = [
      { id: `ticket_${"b".repeat(32)}`, publishState: "hidden", reason: null, status: "pending_verification" },
      { id: `ticket_${"c".repeat(32)}`, publishState: "hidden", reason: "schema_violation", status: "rejected" },
      { id: `ticket_${"d".repeat(32)}`, publishState: "published", reason: null, status: "accepted" },
    ] as const;
    for (const [index, state] of states.entries()) {
      await env.DB.prepare(
        `insert into submissions (
          submission_id, origin, submitter_id, submitter_display_name, github_login, declared_model_slug,
          status, status_reason, raw_bundle_sha256, idempotency_key, publish_state,
          published_at, validated_at, created_at
        ) values (?, 'community', ?, 'Bridge Submitter', 'octocat', 'bridge-model', ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).bind(
        state.id,
        `public_key:${index.toString(16).padStart(64, "0")}`,
        state.status,
        state.reason,
        index.toString(16).padStart(64, "1"),
        index.toString(16).padStart(64, "1"),
        state.publishState,
        state.status === "accepted" ? "2026-07-18 00:00:00" : null,
        state.status === "pending_verification" ? null : "2026-07-18 00:00:00",
        `2026-07-17 00:0${index}:00`,
      ).run();
    }

    const response = await listLifecycle({ env, request: getRequest("/api/submissions/list") });
    expect(response.status).toBe(200);
    const page = parseSubmissionLifecyclePage(await response.json());
    expect(page).not.toBeNull();
    expect(page?.submissions.length).toBe(1);
    const published = page?.submissions.find((entry) => entry.publish_state === "published");
    expect(published?.submission_id).toBe(`ticket_${"d".repeat(32)}`);
    expect(published?.github_login).toBe("octocat");
  });
});

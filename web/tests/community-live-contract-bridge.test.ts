import { describe, expect, it } from "vitest";
import { LiveBoardEnvelopeSchema, LiveBoardRowSchema } from "../lib/board-adapter";
import { COMMUNITY_LIVE_BOARD_KEY } from "../functions/_lib/community-live-board";
import { SubmissionEnvelopeSchema } from "../functions/_lib/submission-contracts";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { parseSubmissionLifecyclePage } from "../lib/submission-lifecycle";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestGet as listLifecycle } from "../functions/api/submissions/list";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { completeProjection, createEnv, getRequest, jsonRequest, sha256Hex } from "./submission-test-support";
import { TEST_IP, communityTicketBody, signedResultBundle, testKeyPair } from "./submission-contract-v2-support";

describe("community live board contract bridge (Track A output vs Track B parser)", () => {
  it("materialized board from a real completed submission parses under the client schemas", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const key = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(key));
    const bundleSha = sha256Hex(bundleJson);
    const ticketResponse = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key, {
        submitter_display_name: "Fixture Submitter",
      }), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const ticket = SubmissionEnvelopeSchema.parse(await ticketResponse.json());
    await env.DB.prepare("update submissions set upload_declared_size_bytes = ? where submission_id = ?")
      .bind(bundleJson.length, ticket.ticket_id)
      .run();
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    const backgroundTasks: Promise<unknown>[] = [];
    const response = await completeSubmission({
      env,
      params: { submissionId: ticket.ticket_id },
      request: jsonRequest(`/api/submissions/${ticket.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "community"),
        raw_bundle_sha256: bundleSha,
        upload_capability: ticket.upload_capability,
      }),
      waitUntil: (task) => { backgroundTasks.push(task); },
    });
    await Promise.all(backgroundTasks);
    expect(response.status).toBe(200);

    const storedBoard = await env.SUBMISSIONS.get(COMMUNITY_LIVE_BOARD_KEY);
    expect(storedBoard).not.toBeNull();
    const board: unknown = JSON.parse(await new Response(storedBoard?.body).text());

    const envelope = LiveBoardEnvelopeSchema.parse(board);
    expect(envelope.schema_version).toBe("localbench.community_live_board.v1");
    expect(envelope.rows.length).toBe(1);
    expect(envelope.omitted_rows).toBe(0);

    const row = LiveBoardRowSchema.parse(envelope.rows[0]);
    expect(row.submission_id).toBe(ticket.ticket_id);
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
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
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

import { describe, expect, it } from "vitest";
import {
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  statusUpdate,
} from "./submission-test-support";
import {
  VALIDATOR_SECRET,
  insertPendingFixture,
  ptmEnv,
  refreshedUpdate,
  storedBoard,
  verifyUpdate,
} from "./publish-then-moderate-test-support";

describe("publish-then-moderate verification flow", () => {
  it("auto-publishes a verified community row and materializes it on the board", async () => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, { submissionId: "ticket_fixture_publish", rawSha: RAW_BUNDLE_SHA, rawJson: RESULT_BUNDLE_JSON });
    const response = await verifyUpdate(env, {
      submissionId: "ticket_fixture_publish",
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    const row = await env.DB.prepare(
      "select status, publish_state, zt1_decision, zt1_coding_state from submissions where submission_id = ?",
    ).bind("ticket_fixture_publish").first();
    const board = await storedBoard(env);

    expect(response.status).toBe(200);
    expect(row).toMatchObject({ status: "accepted", publish_state: "published" });
    expect(row?.["zt1_decision"]).not.toBe("escalated");
    expect(row?.["zt1_coding_state"]).toBe("self_reported_exec");
    expect(board).toMatchObject({ rows: [{ submission_id: "ticket_fixture_publish" }] });
  });

  it("keeps an accepted row hidden when auto-publish is off", async () => {
    const env = await ptmEnv(false);
    await insertPendingFixture(env, { submissionId: "ticket_fixture_auto_off", rawSha: RAW_BUNDLE_SHA, rawJson: RESULT_BUNDLE_JSON });
    const response = await verifyUpdate(env, {
      submissionId: "ticket_fixture_auto_off",
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    const row = await env.DB.prepare("select status, publish_state from submissions where submission_id = ?")
      .bind("ticket_fixture_auto_off").first();
    expect(response.status).toBe(200);
    expect(row).toMatchObject({ status: "accepted", publish_state: "hidden" });
  });

  it("applies a projection-free rejection idempotently without writing projection objects", async () => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, { submissionId: "ticket_fixture_reject", rawSha: RAW_BUNDLE_SHA, rawJson: RESULT_BUNDLE_JSON });
    const update = {
      accepted: false,
      operation: "initial_decision",
      raw_bundle_sha256: RAW_BUNDLE_SHA,
      reason_code: "manifest_invalid",
      reason_detail: "synthetic fixture rejection",
      status: "rejected",
      validated_at: "2026-07-18T00:00:00Z",
      validator_version: "fixture-validator",
    };
    const first = await verifyUpdate(env, { submissionId: "ticket_fixture_reject", update });
    const retry = await verifyUpdate(env, { submissionId: "ticket_fixture_reject", update });
    const row = await env.DB.prepare(
      "select status, status_reason, publish_state, projection_object_sha256 from submissions where submission_id = ?",
    ).bind("ticket_fixture_reject").first();
    const transitions = await env.DB.prepare(
      "select count(*) as count from submission_transitions where submission_id = ? and to_status = 'rejected'",
    ).bind("ticket_fixture_reject").first();

    expect(first.status).toBe(200);
    expect(retry.status).toBe(200);
    expect(row).toMatchObject({
      projection_object_sha256: null,
      publish_state: "hidden",
      status: "rejected",
      status_reason: "manifest_invalid",
    });
    expect(transitions?.["count"]).toBe(1);
  });

  it("refreshes a projection once, audits the validator actor, and treats an identical retry as a no-op", async () => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, { submissionId: "ticket_fixture_refresh", rawSha: RAW_BUNDLE_SHA, rawJson: RESULT_BUNDLE_JSON });
    const initial = await verifyUpdate(env, {
      headers: { "x-localbench-validator-secret": VALIDATOR_SECRET },
      submissionId: "ticket_fixture_refresh",
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    expect(initial.status).toBe(200);
    const before = await env.DB.prepare(
      "select state_revision, projection_object_sha256 from submissions where submission_id = ?",
    ).bind("ticket_fixture_refresh").first();
    const refresh = refreshedUpdate(
      Number(before?.["state_revision"]),
      String(before?.["projection_object_sha256"]),
    );

    const applied = await verifyUpdate(env, { submissionId: "ticket_fixture_refresh", update: refresh });
    const after = await env.DB.prepare(
      "select state_revision, projection_object_sha256 from submissions where submission_id = ?",
    ).bind("ticket_fixture_refresh").first();
    const retry = await verifyUpdate(env, { submissionId: "ticket_fixture_refresh", update: refresh });
    const retried = await env.DB.prepare(
      "select state_revision from submissions where submission_id = ?",
    ).bind("ticket_fixture_refresh").first();
    const transition = await env.DB.prepare(
      "select actor, reason from submission_transitions where submission_id = ? and reason = 'reverified'",
    ).bind("ticket_fixture_refresh").first();
    const board = await storedBoard(env);

    expect(applied.status).toBe(200);
    expect(retry.status).toBe(200);
    expect(after?.["projection_object_sha256"]).not.toBe(before?.["projection_object_sha256"]);
    expect(retried?.["state_revision"]).toBe(after?.["state_revision"]);
    expect(transition).toMatchObject({ actor: "maintainer", reason: "reverified" });
    expect(board).toMatchObject({ rows: [{ model: { display_name: "Refreshed Fixture Model" } }] });
    const initialActor = await env.DB.prepare(
      "select actor from submission_transitions where submission_id = ? and to_status = 'accepted' order by id asc limit 1",
    ).bind("ticket_fixture_refresh").first();
    expect(initialActor).toMatchObject({ actor: "auto-validator" });
  });
});

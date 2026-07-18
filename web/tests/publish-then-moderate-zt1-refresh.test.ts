import { describe, expect, it } from "vitest";
import { canonicalJson } from "../functions/_lib/submission-canonical";
import {
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  sha256Hex,
  statusUpdate,
} from "./submission-test-support";
import {
  insertPendingFixture,
  ptmEnv,
  refreshedUpdate,
  storedBoard,
  verifyUpdate,
} from "./publish-then-moderate-test-support";

describe("publish-then-moderate refresh guards and ZT-1 mapping", () => {
  it.each([
    ["state_revision_mismatch", (revision: number, sha: string) => refreshedUpdate(revision + 1, sha)],
    ["previous_projection_mismatch", (revision: number) => refreshedUpdate(revision, "f".repeat(64))],
    ["validated_at_not_newer", (revision: number, sha: string) => refreshedUpdate(revision, sha, "2026-06-30T00:00:00Z")],
  ] as const)("rejects projection refresh conflicts with %s", async (code, updateFor) => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, {
      rawJson: RESULT_BUNDLE_JSON,
      rawSha: RAW_BUNDLE_SHA,
      submissionId: `ticket_fixture_refresh_${code}`,
    });
    await verifyUpdate(env, {
      submissionId: `ticket_fixture_refresh_${code}`,
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    const row = await env.DB.prepare(
      "select state_revision, projection_object_sha256 from submissions where submission_id = ?",
    ).bind(`ticket_fixture_refresh_${code}`).first();
    const response = await verifyUpdate(env, {
      submissionId: `ticket_fixture_refresh_${code}`,
      update: updateFor(Number(row?.["state_revision"]), String(row?.["projection_object_sha256"])),
    });

    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ code });
  });

  it("holds duplicate artifacts instead of publishing them", async () => {
    const env = await ptmEnv(true);
    await insertPendingFixture(env, {
      rawJson: RESULT_BUNDLE_JSON,
      rawSha: RAW_BUNDLE_SHA,
      submissionId: "ticket_fixture_duplicate_hold",
    });
    await env.DB.prepare("update submissions set duplicate_of = ? where submission_id = ?")
      .bind("ticket_fixture_duplicate_source", "ticket_fixture_duplicate_hold").run();
    const response = await verifyUpdate(env, {
      submissionId: "ticket_fixture_duplicate_hold",
      update: statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
    });
    const row = await env.DB.prepare(
      "select status, publish_state, zt1_decision, zt1_decision_reason from submissions where submission_id = ?",
    ).bind("ticket_fixture_duplicate_hold").first();

    expect(response.status).toBe(200);
    expect(row).toMatchObject({
      publish_state: "hidden",
      status: "accepted",
      zt1_decision: "escalated",
      zt1_decision_reason: "duplicate_artifact",
    });
    expect(await storedBoard(env)).toBeNull();
  });

  it("converts unsafe raw metadata into a projection-free rejection", async () => {
    const env = await ptmEnv(true);
    const bundle = JSON.parse(RESULT_BUNDLE_JSON) as Record<string, unknown>;
    bundle["model"] = { name: "https://fixture.invalid/model" };
    const rawJson = canonicalJson(bundle);
    const rawSha = sha256Hex(rawJson);
    await insertPendingFixture(env, {
      rawJson,
      rawSha,
      submissionId: "ticket_fixture_unsafe_metadata",
    });
    const response = await verifyUpdate(env, {
      submissionId: "ticket_fixture_unsafe_metadata",
      update: statusUpdate("accepted", rawSha, "community"),
    });
    const row = await env.DB.prepare(
      "select status, status_reason, projection_object_sha256, publish_state from submissions where submission_id = ?",
    ).bind("ticket_fixture_unsafe_metadata").first();

    expect(response.status).toBe(200);
    expect(row).toMatchObject({
      projection_object_sha256: null,
      publish_state: "hidden",
      status: "rejected",
      status_reason: "metadata_unsafe",
    });
  });
});

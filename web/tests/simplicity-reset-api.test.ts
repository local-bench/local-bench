import { describe, expect, it } from "vitest";
import { canonicalJson } from "../functions/_lib/submission-canonical";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { parseCommunityLiveBoard, reconcileCommunityRows } from "../lib/community-live";
import { onRequestPost as suppressSubmission } from "../functions/api/admin/submissions/[submissionId]/suppress";
import { onRequestGet as getBoard } from "../functions/api/board/community.json";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestGet as listSubmissions } from "../functions/api/submissions/list";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import {
  ADMIN_SECRET,
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0006,
  MIGRATION_0008,
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  MIGRATION_0012,
  MIGRATION_0013,
  MIGRATION_0014,
  MIGRATION_0015,
  MIGRATION_0016,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  createEnv,
  completeProjection,
  issueEnvelope,
  jsonRequest,
  sha256Hex,
} from "./submission-test-support";
import {
  TEST_IP,
  communityTicketBody,
  signedResultBundle,
  testKeyPair,
} from "./submission-contract-v2-support";

const AXES = ["agentic", "coding", "instruction_following", "knowledge", "math", "tool_calling"] as const;

describe("simplicity reset publish-on-submit API", () => {
  it("publishes and ranks a complete client projection in the materialized board in the same flow", async () => {
    // Given: a community ticket and its content-addressed raw bundle are ready to complete.
    const env = await createResetEnv();
    const key = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(key));
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const ticketBody = await ticket.json();
    const submissionId = requiredString(ticketBody, "ticket_id");
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);

    // When: the client submits its complete accepted_result_projection.v2.
    const response = await completeSubmission({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: clientProjection(bundleSha),
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: publication, ranking, and board materialization are observable immediately.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      origin: "community",
      publish_state: "published",
      status: "published",
    });
    const publishedRow = await env.DB.prepare(
      "select verification_level from submissions where submission_id = ?",
    ).bind(submissionId).first();
    expect(publishedRow).toMatchObject({ verification_level: "client_reported" });
    const board = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    expect(board.status).toBe(200);
    const boardBody = await board.json();
    expect(boardBody).toMatchObject({
      rows: [{
        headline_complete: true,
        origin: "community",
        ranked: true,
        submission_id: submissionId,
        trust: { chip: "self-reported" },
      }],
    });
    const parsedBoard = parseCommunityLiveBoard(boardBody);
    expect(parsedBoard?.rows[0]).toMatchObject({ ranked: true, trust: { chip: "self-reported" } });
    expect(reconcileCommunityRows([], parsedBoard?.rows ?? [])[0]).toMatchObject({ ranked: true });
  });

  it("rejects a projection missing one headline axis as incomplete_run", async () => {
    // Given: a valid community upload whose client projection omits tool calling.
    const env = await createResetEnv();
    const key = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(key));
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const submissionId = requiredString(await ticket.json(), "ticket_id");
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    const projection = clientProjection(bundleSha, ["tool_calling"]);

    // When: the client completes the submission.
    const response = await completeSubmission({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: projection,
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
      }),
    });

    // Then: the row is terminally rejected and never reaches the board.
    expect(response.status).toBe(422);
    expect(await response.json()).toMatchObject({ code: "incomplete_run", status: "rejected" });
    const row = await env.DB.prepare("select status, status_reason, publish_state from submissions where submission_id = ?")
      .bind(submissionId)
      .first();
    expect(row).toMatchObject({ publish_state: "hidden", status: "rejected", status_reason: "incomplete_run" });
    const board = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    expect(await board.json()).toMatchObject({ rows: [] });
  });

  it("keeps suppression effective after immediate publication", async () => {
    // Given: a complete community submission has published in the new flow.
    const env = await createResetEnv();
    const key = testKeyPair();
    const bundleJson = JSON.stringify(signedResultBundle(key));
    const bundleSha = sha256Hex(bundleJson);
    const ticket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(bundleSha, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const submissionId = requiredString(await ticket.json(), "ticket_id");
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    await completeSubmission({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: clientProjection(bundleSha),
        raw_bundle_sha256: bundleSha,
      }),
    });

    // When: a maintainer suppresses the published row.
    const response = await suppressSubmission({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/admin/submissions/${submissionId}/suppress`, { reason: "evidence received" }, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });

    // Then: the lifecycle is suppressed and the rebuilt board no longer contains the row.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "suppressed" });
    const board = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    expect(await board.json()).toMatchObject({ rows: [] });
  });

  it("interleaves maintainer and community rows by composite with one origin-derived chip", async () => {
    // Given: one maintainer run and one community run have distinct complete projections.
    const env = await createResetEnv();
    const anchorBundle = JSON.stringify({ fixture: "maintainer" });
    const anchorSha = sha256Hex(anchorBundle);
    const anchorTicket = await issueEnvelope(env, anchorSha);
    await env.SUBMISSIONS.put(rawBundleKey(anchorSha), anchorBundle);
    const key = testKeyPair();
    const communityBundle = JSON.stringify(signedResultBundle(key, { fixture: "community" }));
    const communitySha = sha256Hex(communityBundle);
    const communityTicket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(communitySha, key), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const communityId = requiredString(await communityTicket.json(), "ticket_id");
    await env.SUBMISSIONS.put(rawBundleKey(communitySha), communityBundle);

    // When: both clients complete, with the community score higher than the maintainer score.
    await completeSubmission({
      env,
      params: { submissionId: anchorTicket.ticket_id },
      request: jsonRequest(`/api/submissions/${anchorTicket.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(anchorSha, "project_anchor", 0.61),
        raw_bundle_sha256: anchorSha,
      }),
    });
    await completeSubmission({
      env,
      params: { submissionId: communityId },
      request: jsonRequest(`/api/submissions/${communityId}/complete`, {
        accepted_result_projection: completeProjection(communitySha, "community", 0.83),
        raw_bundle_sha256: communitySha,
      }),
    });

    // Then: one board orders both origins by composite and exposes no trust-tier fields.
    const response = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    const body = await response.json();
    expect(body).toMatchObject({ rows: [
      { origin: "community", scores: { composite_full: 0.83 } },
      { origin: "project_anchor", scores: { composite_full: 0.61 } },
    ] });
    const rows = requiredRows(body);
    expect(rows.map((row) => row["trust"])).toEqual([
      { chip: "self-reported" },
      { chip: "maintainer-run" },
    ]);
    const parsed = parseCommunityLiveBoard(body);
    expect(parsed?.droppedRows).toBe(0);
    expect(parsed?.rows.map((row) => row.origin)).toEqual(["community", "project_anchor"]);
  });

  it("lists the published lifecycle without a ZT-1 hold flag", async () => {
    // Given: a complete maintainer submission has published.
    const env = await createResetEnv();
    const bundle = JSON.stringify({ fixture: "lifecycle" });
    const bundleSha = sha256Hex(bundle);
    const ticket = await issueEnvelope(env, bundleSha);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundle);
    await completeSubmission({
      env,
      params: { submissionId: ticket.ticket_id },
      request: jsonRequest(`/api/submissions/${ticket.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "project_anchor"),
        raw_bundle_sha256: bundleSha,
      }),
    });

    // When: the public lifecycle endpoint is read.
    const response = await listSubmissions({
      env,
      request: new Request("https://local-bench.ai/api/submissions/list"),
    });

    // Then: the row is published and the deleted hold concept is absent.
    const body = await response.json();
    const row = requiredRows(body, "submissions")[0];
    expect(row).toMatchObject({ status: "published" });
    expect(row).not.toHaveProperty("held_for_review");
  });

  it("accepts client_reported additively without invalidating legacy verification levels", () => {
    // Given: new client-reported and old bundle-rescored projection contracts.
    const clientReported = completeProjection("c".repeat(64), "community");
    const bundleRescored = { ...clientReported, verification_level: "bundle_rescored" };
    const spotReproduced = { ...clientReported, verification_level: "spot_reproduced" };

    // When / Then: all supported values parse through the shared Zod boundary.
    expect(AcceptedResultProjectionV2Schema.safeParse(clientReported).success).toBe(true);
    expect(AcceptedResultProjectionV2Schema.safeParse(bundleRescored).success).toBe(true);
    expect(AcceptedResultProjectionV2Schema.safeParse(spotReproduced).success).toBe(true);
  });
});

function createResetEnv() {
  return createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002,
      MIGRATION_0004,
      MIGRATION_0005,
      MIGRATION_0006,
      MIGRATION_0008,
      MIGRATION_0009,
      MIGRATION_0010,
      MIGRATION_0011,
      MIGRATION_0012,
      MIGRATION_0013,
      MIGRATION_0014,
      MIGRATION_0015,
      MIGRATION_0016,
    ],
  });
}

function clientProjection(bundleSha: string, omittedAxes: readonly (typeof AXES)[number][] = []): Record<string, unknown> {
  const measuredAxes = AXES.filter((axis) => !omittedAxes.includes(axis));
  const complete = measuredAxes.length === AXES.length;
  const hashable = {
    schema_version: "localbench.accepted_result_projection.v2",
    model: {
      declared_name: "Reset Community Model",
      display_name: "Reset Community Model",
      file_sha256: "a".repeat(64),
      identity_status: "unverified",
      model_system_key: `artifact:${"a".repeat(64)}`,
    },
    lineage: { base_model: ["Base Model"] },
    runtime: { name: "llama.cpp", version: "b-reset" },
    suite_release_id: SUITE_RELEASE_ID,
    suite_manifest_sha256: SUITE_MANIFEST_SHA,
    scorecard_id: "local-intelligence-index-v4.1",
    coverage_profile_id: "full-exec-6axis-v1",
    index_version: "index-v4.1",
    headline_complete: complete,
    scores: {
      headline_score: complete ? 0.71 : null,
      partial_composite: 0.71,
      partial_composite_scope: "measured_headline_axes",
      measured_headline_weight: complete ? 1 : 0.85,
      missing_headline_weight: complete ? 0 : 0.15,
      known_headline_contribution: complete ? 0.71 : 0.6035,
      rank_scope: "full-exec-6axis-v1",
      composite_full: complete ? 0.71 : null,
    },
    axes: Object.fromEntries(measuredAxes.map((axis) => [axis, {
      ci: [0.69, 0.73],
      n: 10,
      score: 0.71,
      status: "measured",
    }])),
    conformance: { status: "passed" },
    receipt_references: { coding_receipt_sha256: "b".repeat(64) },
    artifact_hashes: {
      bundle_sha256: bundleSha,
      projection_sha256: "",
      public_artifact_manifest_sha256: "",
    },
    origin: "community",
    trust_label: "community_self_submitted",
    verification_level: "client_reported",
    agentic_provenance: "self_reported",
    rescore_modes: {
      amo: "rescored",
      appworld_c: "verdict_carried",
      bigcodebench_hard: "verdict_carried",
      ifbench: "rescored",
      mmlu_pro: "rescored",
      olymmath_hard: "rescored",
      tc_json_v1: "rescored",
    },
    validator: {
      validator_version: "localbench-cli-0.4.3.dev0",
      commit: "reset-api-test",
      validated_at: "2026-07-19T00:00:00Z",
    },
  } as const;
  const projectionSha = sha256Hex(canonicalJson(hashable));
  const projection = {
    ...hashable,
    artifact_hashes: {
      bundle_sha256: bundleSha,
      projection_sha256: projectionSha,
      public_artifact_manifest_sha256: sha256Hex(canonicalJson({
        bundle_sha256: bundleSha,
        projection_sha256: projectionSha,
      })),
    },
  };
  return projection;
}

function requiredString(value: unknown, key: string): string {
  if (typeof value !== "object" || value === null) throw new Error(`${key} missing`);
  const field = Object.entries(value).find(([entryKey]) => entryKey === key)?.[1];
  if (typeof field !== "string") throw new Error(`${key} must be a string`);
  return field;
}

function requiredRows(value: unknown, key = "rows"): readonly Record<string, unknown>[] {
  if (typeof value !== "object" || value === null) throw new Error(`${key} missing`);
  const rows = Object.entries(value).find(([entryKey]) => entryKey === key)?.[1];
  if (!Array.isArray(rows) || rows.some((row) => typeof row !== "object" || row === null)) {
    throw new Error(`${key} must contain objects`);
  }
  return rows;
}

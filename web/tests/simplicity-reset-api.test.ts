import { describe, expect, it } from "vitest";
import { canonicalJson } from "../functions/_lib/submission-canonical";
import { AcceptedResultProjectionV2Schema, type SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import { COMMUNITY_LIVE_BOARD_KEY } from "../functions/_lib/community-live-board";
import { projectionKey, rawBundleKey } from "../functions/_lib/submission-storage";
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
  MIGRATION_0017,
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
  it("rejects submitter-supplied link fields while accepting structured HF identity", () => {
    const projection = clientProjection("b".repeat(64), {
      hf: {
        filename: "weights/model.gguf",
        repo: "localbench/reset-fixture",
        revision: "c".repeat(40),
      },
    });
    const model = projection["model"];
    if (typeof model !== "object" || model === null || Array.isArray(model)) {
      throw new TypeError("projection fixture model must be a record");
    }
    const withLink = structuredClone(projection);
    const linkedModel = withLink["model"];
    if (typeof linkedModel !== "object" || linkedModel === null || Array.isArray(linkedModel)) {
      throw new TypeError("cloned projection fixture model must be a record");
    }
    Object.assign(linkedModel, { artifact_url: "https://example.invalid/model.gguf" });

    expect(AcceptedResultProjectionV2Schema.safeParse(projection).success).toBe(true);
    expect(AcceptedResultProjectionV2Schema.safeParse(withLink).success).toBe(false);
  });

  it("recomputes and persists the authoritative index-v4.1 composite from all six axes", async () => {
    // Given: a complete projection carries structured HF identity but advisory composites drift from its axes.
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
    const uploadCapability = requiredString(ticketBody, "upload_capability");
    await prepareDirectUpload(env, submissionId, bundleJson.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    const projection = clientProjection(bundleSha, {
      axisScores: {
        agentic: 0.9,
        coding: 0.7,
        instruction_following: 0.6,
        knowledge: 0.8,
        math: 0.4,
        tool_calling: 0.2,
      },
      clientComposite: 0.5,
      hf: {
        filename: "weights/model-q4_k_m.gguf",
        repo: "localbench/reset-fixture",
        revision: "c".repeat(40),
      },
    });

    // When: the client completes through the ordinary community path.
    const response = await completeAndRebuild({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: projection,
        raw_bundle_sha256: bundleSha,
        upload_capability: uploadCapability,
      }),
    });

    // Then: the stored projection, D1 reference, and ranking surface all use the server result.
    expect(response.status).toBe(200);
    const storedRow = await env.DB.prepare(
      "select projection_object_sha256, projection_sha256 from submissions where submission_id = ?",
    ).bind(submissionId).first();
    const objectSha = requiredString(storedRow, "projection_object_sha256");
    const storedObject = await env.SUBMISSIONS.get(projectionKey(objectSha));
    expect(storedObject).not.toBeNull();
    const storedProjection = AcceptedResultProjectionV2Schema.parse(
      JSON.parse(await new Response(storedObject?.body).text()),
    );
    expect(storedProjection.scores).toMatchObject({
      composite_full: 0.7275,
      headline_score: 0.7275,
      partial_composite: 0.7275,
    });
    expect(storedProjection.model.hf).toEqual({
      filename: "weights/model-q4_k_m.gguf",
      repo: "localbench/reset-fixture",
      revision: "c".repeat(40),
    });
    expect(storedProjection.normalization_annotations).toEqual([{
      client_values: { composite_full: 0.5, headline_score: 0.5, partial_composite: 0.5 },
      code: "client_composite_drift",
      fields: ["headline_score", "partial_composite", "composite_full"],
      server_value: 0.7275,
    }]);
    expect(storedRow).toMatchObject({ projection_sha256: storedProjection.artifact_hashes.projection_sha256 });
    const board = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    expect(await board.json()).toMatchObject({
      rows: [{ model: { hf: storedProjection.model.hf }, ranked: true, scores: { headline_score: 0.7275 } }],
    });
  });

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
    const uploadCapability = requiredString(ticketBody, "upload_capability");
    await prepareDirectUpload(env, submissionId, bundleJson.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);

    // When: the client submits its complete accepted_result_projection.v2.
    const response = await completeAndRebuild({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: clientProjection(bundleSha),
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
        upload_capability: uploadCapability,
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
      }],
    });
    const parsedBoard = parseCommunityLiveBoard(boardBody);
    expect(parsedBoard?.rows[0]).toMatchObject({ headlineComplete: true });
    expect(parsedBoard?.rows[0]).not.toHaveProperty("trust");
    expect(reconcileCommunityRows([], parsedBoard?.rows ?? [])[0]).toMatchObject({ headlineComplete: true });
  });

  it("returns the published response when the post-publish board rebuild fails", async () => {
    // Given: publication storage works but the materialized board write will reject.
    const baseEnv = await createResetEnv();
    const env = boardWriteFailureEnv(baseEnv);
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
    const uploadCapability = requiredString(ticketBody, "upload_capability");
    await prepareDirectUpload(env, submissionId, bundleJson.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    const backgroundTasks: Promise<unknown>[] = [];
    const context = {
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: clientProjection(bundleSha),
        raw_bundle_sha256: bundleSha,
        upload_capability: uploadCapability,
      }),
      waitUntil: (task: Promise<unknown>) => { backgroundTasks.push(task); },
    };

    // When: completion publishes the D1 row and schedules materialization.
    const response = await completeSubmission(context);

    // Then: the response remains successful and the contained background failure is observable only as completed work.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "published" });
    expect(backgroundTasks).toHaveLength(1);
    await expect(Promise.all(backgroundTasks)).resolves.toHaveLength(1);
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
    const ticketBody = await ticket.json();
    const submissionId = requiredString(ticketBody, "ticket_id");
    const uploadCapability = requiredString(ticketBody, "upload_capability");
    await prepareDirectUpload(env, submissionId, bundleJson.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    const projection = clientProjection(bundleSha, { omittedAxes: ["math"] });

    // When: the client completes the submission.
    const response = await completeAndRebuild({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: projection,
        raw_bundle_sha256: bundleSha,
        size_bytes: bundleJson.length,
        upload_capability: uploadCapability,
      }),
    });

    // Then: the row is terminally rejected and never reaches the board.
    expect(response.status).toBe(422);
    expect(await response.json()).toMatchObject({
      code: "incomplete_run",
      error: "all 5 headline axes must be measured",
      status: "rejected",
    });
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
    const ticketBody = await ticket.json();
    const submissionId = requiredString(ticketBody, "ticket_id");
    const uploadCapability = requiredString(ticketBody, "upload_capability");
    await prepareDirectUpload(env, submissionId, bundleJson.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
    await completeAndRebuild({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/submissions/${submissionId}/complete`, {
        accepted_result_projection: clientProjection(bundleSha),
        raw_bundle_sha256: bundleSha,
        upload_capability: uploadCapability,
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

  it("interleaves both origins with only a project-run badge and explicitly unverified handles", async () => {
    // Given: one maintainer run and one community run have distinct complete projections.
    const env = await createResetEnv();
    const anchorBundle = JSON.stringify({ fixture: "maintainer" });
    const anchorSha = sha256Hex(anchorBundle);
    const anchorTicket = await issueEnvelope(
      env,
      anchorSha,
      { submitter_display_name: "Anchor Operator" },
      anchorBundle.length,
    );
    await env.SUBMISSIONS.put(rawBundleKey(anchorSha), anchorBundle);
    const key = testKeyPair();
    const communityBundle = JSON.stringify(signedResultBundle(key, { fixture: "community" }));
    const communitySha = sha256Hex(communityBundle);
    const communityTicket = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody(communitySha, key, {
        submitter_display_name: "Community Runner",
      }), {
        "CF-Connecting-IP": TEST_IP,
      }),
    });
    const communityEnvelope = await communityTicket.json();
    const communityId = requiredString(communityEnvelope, "ticket_id");
    const communityUploadCapability = requiredString(communityEnvelope, "upload_capability");
    await prepareDirectUpload(env, communityId, communityBundle.length);
    await env.SUBMISSIONS.put(rawBundleKey(communitySha), communityBundle);

    // When: both clients complete, with the community score higher than the maintainer score.
    await completeAndRebuild({
      env,
      params: { submissionId: anchorTicket.ticket_id },
      request: jsonRequest(`/api/submissions/${anchorTicket.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(anchorSha, "project_anchor", 0.61),
        raw_bundle_sha256: anchorSha,
        upload_capability: anchorTicket.upload_capability,
      }),
    });
    await completeAndRebuild({
      env,
      params: { submissionId: communityId },
      request: jsonRequest(`/api/submissions/${communityId}/complete`, {
        accepted_result_projection: completeProjection(communitySha, "community", 0.83),
        raw_bundle_sha256: communitySha,
        upload_capability: communityUploadCapability,
      }),
    });

    // Then: one board orders both origins by composite without assigning a community trust tier.
    const response = await getBoard({ env, request: new Request("https://local-bench.ai/api/board/community.json") });
    const body = await response.json();
    expect(body).toMatchObject({ rows: [
      { origin: "community", scores: { composite_full: 0.83 } },
      { origin: "project_anchor", scores: { composite_full: 0.61 } },
    ] });
    const rows = requiredRows(body);
    expect(rows[0]).not.toHaveProperty("badge");
    expect(rows[0]?.["submitter"]).toMatchObject({ unverified_handle: "Community Runner" });
    expect(rows[1]).toMatchObject({
      badge: "project-run",
      submitter: { unverified_handle: "Anchor Operator" },
    });
    expect(rows.every((row) => !("trust" in row))).toBe(true);
    expect(JSON.stringify(rows)).not.toMatch(/self-reported|maintainer-run|re-scored|maintainer_verified/u);
    const parsed = parseCommunityLiveBoard(body);
    expect(parsed?.droppedRows).toBe(0);
    expect(parsed?.rows.map((row) => row.origin)).toEqual(["community", "project_anchor"]);
  });

  it("lists the published lifecycle without a ZT-1 hold flag", async () => {
    // Given: a complete maintainer submission has published.
    const env = await createResetEnv();
    const bundle = JSON.stringify({ fixture: "lifecycle" });
    const bundleSha = sha256Hex(bundle);
    const ticket = await issueEnvelope(env, bundleSha, {}, bundle.length);
    await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundle);
    await completeAndRebuild({
      env,
      params: { submissionId: ticket.ticket_id },
      request: jsonRequest(`/api/submissions/${ticket.ticket_id}/complete`, {
        accepted_result_projection: completeProjection(bundleSha, "project_anchor"),
        raw_bundle_sha256: bundleSha,
        upload_capability: ticket.upload_capability,
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
      MIGRATION_0017,
    ],
  });
}

type ClientProjectionOptions = {
  readonly axisScores?: Readonly<Record<(typeof AXES)[number], number>>;
  readonly clientComposite?: number;
  readonly hf?: {
    readonly filename: string;
    readonly repo: string;
    readonly revision: string;
  };
  readonly omittedAxes?: readonly (typeof AXES)[number][];
};

function clientProjection(bundleSha: string, options: ClientProjectionOptions = {}): Record<string, unknown> {
  const omittedAxes = options.omittedAxes ?? [];
  const measuredAxes = AXES.filter((axis) => !omittedAxes.includes(axis));
  const complete = measuredAxes.length === AXES.length;
  const clientComposite = options.clientComposite ?? 0.71;
  const hashable = {
    schema_version: "localbench.accepted_result_projection.v2",
    model: {
      declared_name: "Reset Community Model",
      display_name: "Reset Community Model",
      file_sha256: "a".repeat(64),
      ...(options.hf === undefined ? {} : { hf: options.hf }),
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
      headline_score: complete ? clientComposite : null,
      partial_composite: clientComposite,
      partial_composite_scope: "measured_headline_axes",
      measured_headline_weight: complete ? 1 : 0.85,
      missing_headline_weight: complete ? 0 : 0.15,
      known_headline_contribution: complete ? clientComposite : clientComposite * 0.85,
      rank_scope: "full-exec-6axis-v1",
      composite_full: complete ? clientComposite : null,
    },
    axes: Object.fromEntries(measuredAxes.map((axis) => [axis, {
      ci: null,
      n: 10,
      score: options.axisScores?.[axis] ?? 0.71,
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

function boardWriteFailureEnv(env: SubmissionApiEnv): SubmissionApiEnv {
  return {
    ...env,
    SUBMISSIONS: {
      delete: (key) => env.SUBMISSIONS.delete(key),
      get: (key) => env.SUBMISSIONS.get(key),
      put: async (key, value, options) => {
        if (key === COMMUNITY_LIVE_BOARD_KEY) throw new TypeError("board write fixture failure");
        return env.SUBMISSIONS.put(key, value, options);
      },
    },
  };
}

async function completeAndRebuild(
  context: Parameters<typeof completeSubmission>[0],
): Promise<Response> {
  const tasks: Promise<unknown>[] = [];
  const response = await completeSubmission({
    ...context,
    waitUntil: (task) => { tasks.push(task); },
  });
  await Promise.all(tasks);
  return response;
}

async function prepareDirectUpload(env: SubmissionApiEnv, submissionId: string, sizeBytes: number): Promise<void> {
  await env.DB.prepare("update submissions set upload_declared_size_bytes = ? where submission_id = ?")
    .bind(sizeBytes, submissionId)
    .run();
}

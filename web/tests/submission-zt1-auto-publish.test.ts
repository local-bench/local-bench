import { describe, expect, it } from "vitest";
import { handleApplyVerificationUpdate } from "../functions/_lib/submission-api";
import { handleAcceptedFeed } from "../functions/_lib/submission-feed-api";
import { rawBundleKey } from "../functions/_lib/submission-storage";
import { handleDigest, handlePublishBatch } from "../functions/_lib/submission-zt1-admin-api";
import {
  ADMIN_SECRET,
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0006,
  MIGRATION_0007,
  MIGRATION_0008,
  PROJECTION_SHA,
  applyMigration,
  columnCount,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
  resultBundle,
  sha256Hex,
  statusUpdate,
} from "./submission-test-support";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";

const KNOWN_HASH = "a".repeat(64);
const UNKNOWN_HASH = "b".repeat(64);

describe("ZT-1 automatic publish decisions", () => {
  it("marks low-impact accepted rows publishable when every auto-accept gate is green", async () => {
    // Given: auto-publish is enabled and the accepted bundle resolves to a known catalog artifact.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({ fileSha: KNOWN_HASH, score: 62 }));

    // When: the verifier applies an accepted status update.
    const response = await verifyAccepted(env, submissionId);

    // Then: ZT-1 leaves the row preview-visible and eligible for the daily publish batch.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_identity_key: "qwen3-4b",
      identity_class: "known_artifact",
      publish_state: "preview",
      zt1_decision: "publishable",
    });
    await expectDecisionLog(env, submissionId, "auto_accept", "publishable");
  }, 15_000);

  it("does not auto-accept duplicate rows", async () => {
    // Given: a duplicate accepted row reaches the verifier route.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({ fileSha: KNOWN_HASH, score: 61 }));
    await env.DB.prepare("update submissions set duplicate_of = 'ticket_existing' where submission_id = ?")
      .bind(submissionId)
      .run();

    // When: the accepted status update is applied.
    const response = await verifyAccepted(env, submissionId);

    // Then: the row is escalated for ZT-2 instead of joining the publish batch.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "hidden",
      zt1_decision: "escalated",
      zt1_decision_reason: "duplicate_flag",
    });
  });

  it("creates an unverified identity row without merging into a catalog slug", async () => {
    // Given: the model artifact hash is not in the known catalog map.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "Community Tiny Q4",
      fileSha: UNKNOWN_HASH,
      score: 55,
      submitterDisplayName: "Ava Bench",
    }), "Ava Bench");

    // When: the accepted status update is applied.
    const response = await verifyAccepted(env, submissionId);

    // Then: the board identity is keyed by artifact hash with an unverified provisional label.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_display_label: "community-declared · identity unverified · Ava Bench",
      board_identity_key: UNKNOWN_HASH,
      identity_class: "unverified",
      provisional_reason: "unknown_identity",
      zt1_decision: "provisional",
    });
  });

  it("escalates protected official-looking names", async () => {
    // Given: an unknown artifact claims a protected family name.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "Qwen3 4B Official",
      family: "Qwen3",
      fileSha: UNKNOWN_HASH,
      score: 58,
    }));

    // When: verification accepts the bundle.
    const response = await verifyAccepted(env, submissionId);

    // Then: ZT-1 parks it for owner-only review.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      identity_class: "protected",
      publish_state: "hidden",
      zt1_decision: "escalated",
      zt1_decision_reason: "protected_identity",
    });
  });

  it("marks self-reported agentic rows provisional", async () => {
    // Given: an otherwise low-impact accepted bundle carries an agentic result.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      agentic: true,
      fileSha: KNOWN_HASH,
      score: 52,
    }));

    // When: verification accepts the bundle.
    const response = await verifyAccepted(env, submissionId);

    // Then: the row is visible only as a 24-hour provisional row.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      provisional_reason: "self_reported_agentic",
      publish_state: "preview",
      zt1_decision: "provisional",
    });
    expect(Date.parse(String(body.provisional_until))).toBeGreaterThan(Date.now() + 23 * 60 * 60 * 1000);
    expect(Date.parse(String(body.provisional_until))).toBeLessThan(Date.now() + 25 * 60 * 60 * 1000);
  }, 15_000);

  it.each([
    ["top_10_overall", seedBoardScores(10, { scoreAt: 10, value: 50 })],
    ["top_3_size_class", seedSizeClassScores("7b", [70, 65, 60])],
    ["family_number_one", seedFamilyScores("BenchFam", [59])],
    ["beats_prior_number_one", seedBoardScores(1, { scoreAt: 1, value: 60 })],
    ["first_page_first_time_key", seedBoardScores(9, { scoreAt: 9, value: 50 })],
  ])("marks %s high-impact rows provisional", async (reason, seed) => {
    // Given: existing board rows make the accepted row high-impact for one trigger.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    await seed(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "BenchFam 7B Q4",
      family: "BenchFam",
      fileSha: KNOWN_HASH,
      fileSizeBytes: 7_000_000_000,
      score: reason === "beats_prior_number_one" ? 62 : 80,
    }));

    // When: verification accepts it.
    const response = await verifyAccepted(env, submissionId);

    // Then: it is visible only as provisional and excluded from batch promotion.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      provisional_reason: expect.stringContaining(reason),
      publish_state: "preview",
      zt1_decision: "provisional",
    });
    const minimumWindowHours = reason === "first_page_first_time_key" ? 23 : 71;
    expect(Date.parse(String(body.provisional_until))).toBeGreaterThan(Date.now() + minimumWindowHours * 60 * 60 * 1000);
  }, 15_000);

  it("caps daily publish batches at 10 and skips provisional rows", async () => {
    // Given: eleven publishable rows and one provisional row are waiting in preview.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    for (let index = 0; index < 11; index += 1) {
      await seedAcceptedDecision(env, `publishable_${index}`, "publishable");
    }
    await env.DB.prepare("update submissions set validated_at = datetime('now', '-2 days') where submission_id like 'publishable_%'").run();
    await seedAcceptedDecision(env, "provisional_1", "provisional");

    // When: the cron/admin batch endpoint runs.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: only ten non-provisional rows are promoted.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      promoted: expect.arrayContaining([
        expect.objectContaining({ submission_id: "publishable_0" }),
      ]),
      skipped_provisional: ["provisional_1"],
    });
    const published = await env.DB.prepare("select count(*) as count from submissions where publish_state = 'published'").first();
    expect(published).toMatchObject({ count: 10 });
  }, 15_000);

  it.each([
    ["pending_gt_20", async (env: SubmissionApiEnv) => seedPending(env, 21)],
    ["submissions_24h_gt_50", async (env: SubmissionApiEnv) => seedRecentSubmissions(env, 51)],
    ["r2_ingress_24h_gt_2gib", async (env: SubmissionApiEnv) => seedIngress(env, 2_147_483_649)],
    ["escalations_24h_gt_10", async (env: SubmissionApiEnv) => seedDecisionRows(env, 11, "escalated")],
    ["accepts_24h_gt_10", async (env: SubmissionApiEnv) => seedAcceptedRows(env, 11)],
    ["sybil_pattern_flag", async (env: SubmissionApiEnv) => seedFlaggedRow(env, "sybil_pattern")],
  ])("freezes auto-publish on %s", async (alarm, seed) => {
    // Given: one freeze threshold is breached.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    await seed(env);

    // When: the batch endpoint evaluates alarms.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: the one-way kill-switch is flipped off by security and logged for the digest.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ alarms: [expect.objectContaining({ reason: alarm })] });
    const setting = await env.DB.prepare("select value, disabled_by from ops_settings where key = 'auto_publish'").first();
    expect(setting).toEqual({ disabled_by: "security", value: "off" });
  }, 15_000);

  it("returns the owner digest read model", async () => {
    // Given: recent accepted, rejected, escalated, elapsed provisional, and alarm rows exist.
    const env = await createZt1Env();
    await seedAcceptedDecision(env, "accepted_1", "publishable");
    await seedRejected(env, "rejected_1", "schema");
    await seedAcceptedDecision(env, "escalated_1", "escalated");
    await seedAcceptedDecision(env, "provisional_elapsed_1", "provisional");
    await env.DB.prepare("update submissions set provisional_until = datetime('now', '-1 hour'), provisional_reason = 'top_10_overall' where submission_id = 'provisional_elapsed_1'").run();
    await env.DB.prepare("insert into submission_decision_log (submission_id, actor, event, reason, details_json) values (null, 'security', 'alarm', 'pending_gt_20', '{}')").run();

    // When: the admin digest endpoint is called.
    const response = await handleDigest(adminGet("/api/admin/digest"), env);

    // Then: it returns row ids and reasons grouped for owner review.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      alarms: [expect.objectContaining({ reason: "pending_gt_20" })],
      escalations: [expect.objectContaining({ submission_id: "escalated_1" })],
      provisional_elapsed: [expect.objectContaining({ submission_id: "provisional_elapsed_1", reason: "top_10_overall" })],
      rejects: [expect.objectContaining({ submission_id: "rejected_1", reason: "schema" })],
    });
    expect(body.accepts).toEqual(expect.arrayContaining([
      expect.objectContaining({ submission_id: "accepted_1", reason: "publishable" }),
    ]));
  });

  it("keeps provisional rows out of the default public feed and exposes the incoming view", async () => {
    // Given: one ranked row and one provisional row are accepted.
    const env = await createZt1Env();
    await seedAcceptedDecision(env, "ranked_1", "publishable", "published");
    await seedAcceptedDecision(env, "provisional_1", "provisional", "preview");

    // When: the public feed is read in default and provisional modes.
    const ranked = await handleAcceptedFeed(getRequest("/api/feed/accepted.json"), env);
    const incoming = await handleAcceptedFeed(getRequest("/api/feed/accepted.json?view=provisional"), env);

    // Then: provisional rows are not mixed into the default verified feed.
    expect(await ranked.json()).toMatchObject({ submissions: [expect.objectContaining({ submission_id: "ranked_1" })] });
    expect(await incoming.json()).toMatchObject({ submissions: [expect.objectContaining({ submission_id: "provisional_1" })] });
  });

  it("adds the ZT-1 columns additively after older rows already exist", async () => {
    // Given: the feedback migration already owns 0007 in this repository.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    for (const migration of [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0007]) {
      await applyMigration(env.DB, migration);
    }
    await issueEnvelope(env);

    // When: the ZT-1 migration is applied after old rows exist.
    await applyMigration(env.DB, MIGRATION_0008);

    // Then: the new columns are nullable and old rows parse through the public row schema.
    expect(await columnCount(env.DB, "submissions", "identity_class")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "board_identity_key")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "provisional_until")).toBe(1);
    const row = await env.DB.prepare("select identity_class, board_identity_key, provisional_until from submissions limit 1").first();
    expect(row).toEqual({ board_identity_key: null, identity_class: null, provisional_until: null });
  });
});

async function createZt1Env(): Promise<SubmissionApiEnv> {
  const env = await createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0007, MIGRATION_0008],
  });
  return {
    ...env,
    ZT1_KNOWN_ARTIFACTS_JSON: JSON.stringify({ [KNOWN_HASH]: "qwen3-4b" }),
    ZT1_PROTECTED_MODEL_PATTERNS_JSON: JSON.stringify(["qwen", "gemma", "llama", "deepseek", "mistral", "phi"]),
  };
}

async function enableAutoPublish(env: SubmissionApiEnv): Promise<void> {
  await env.DB.prepare(
    "insert into ops_settings (key, value, disabled_by, updated_at) values ('auto_publish', 'on', null, datetime('now')) on conflict(key) do update set value = 'on', disabled_by = null, updated_at = datetime('now')",
  ).run();
}

async function ticketWithBundle(
  env: SubmissionApiEnv,
  bundle: Record<string, unknown>,
  submitterDisplayName?: string,
): Promise<string> {
  const bundleJson = JSON.stringify(bundle);
  const bundleSha = sha256Hex(bundleJson);
  const envelope = await issueEnvelope(env, bundleSha, { submitter_display_name: submitterDisplayName });
  await env.SUBMISSIONS.put(rawBundleKey(bundleSha), bundleJson);
  await env.DB.prepare(
    `update submissions set
      status = 'pending_verification',
      raw_bundle_size_bytes = ?,
      run_payload_sha256 = ?,
      uploaded_at = datetime('now')
     where submission_id = ?`,
  )
    .bind(bundleJson.length, sha256Hex(`${bundleJson}:payload`), envelope.ticket_id)
    .run();
  return envelope.ticket_id;
}

async function verifyAccepted(env: SubmissionApiEnv, submissionId: string): Promise<Response> {
  const row = await env.DB.prepare("select raw_bundle_sha256 from submissions where submission_id = ?")
    .bind(submissionId)
    .first();
  const rawBundleSha = row?.["raw_bundle_sha256"];
  if (typeof rawBundleSha !== "string") {
    throw new Error("submission fixture did not store raw bundle sha");
  }
  return handleApplyVerificationUpdate(
    adminJson(`/api/admin/submissions/${submissionId}/verification`, {
      ...statusUpdate("accepted"),
      raw_bundle_sha256: rawBundleSha,
    }),
    env,
    {
    submissionId,
    },
  );
}

function bundleFor(options: {
  readonly agentic?: boolean;
  readonly displayName?: string;
  readonly family?: string;
  readonly fileSha: string;
  readonly fileSizeBytes?: number;
  readonly score: number;
  readonly submitterDisplayName?: string;
}): Record<string, unknown> {
  const bundle = resultBundle();
  bundle["model"] = { name: options.displayName ?? "Community Tiny Q4" };
  bundle["scores"] = {
    headline_score: options.score,
    known_headline_contribution: options.score,
    measured_headline_weight: 1,
    missing_headline_weight: 0,
    partial_composite: options.score,
    partial_composite_scope: "measured_headline_axes",
    rank_scope: "full-exec-6axis-v1",
  };
  const manifest = bundle["manifest"];
  if (!isRecord(manifest)) {
    throw new Error("result bundle manifest fixture must be an object");
  }
  bundle["manifest"] = {
    ...manifest,
    model: {
      chat_template_digest: "c".repeat(64),
      family: options.family ?? "Community",
      file_name: "model.gguf",
      file_sha256: options.fileSha,
      file_size_bytes: options.fileSizeBytes ?? 4_000_000_000,
      format: "gguf",
      quant_label: "Q4_K_M",
      tokenizer_digest: "d".repeat(64),
    },
  };
  if (options.submitterDisplayName !== undefined) {
    bundle["submitter_display_name"] = options.submitterDisplayName;
  }
  if (options.agentic === true) {
    bundle["items"] = [{ bench: "appworld_c", item_id: "appworld-low-impact", response: "completed" }];
  }
  return bundle;
}

function adminJson(path: string, body: unknown): Request {
  return jsonRequest(path, body, { "x-localbench-admin-secret": ADMIN_SECRET });
}

function adminGet(path: string): Request {
  return getRequest(path, { "x-localbench-admin-secret": ADMIN_SECRET });
}

async function expectDecisionLog(env: SubmissionApiEnv, submissionId: string, event: string, reason: string): Promise<void> {
  const row = await env.DB.prepare(
    "select event, reason from submission_decision_log where submission_id = ? order by id desc limit 1",
  )
    .bind(submissionId)
    .first();
  expect(row).toEqual({ event, reason });
}

function seedBoardScores(count: number, options: { readonly scoreAt: number; readonly value: number }) {
  return async (env: SubmissionApiEnv): Promise<void> => {
    for (let index = 1; index <= count; index += 1) {
      await insertBoardEntry(env, `board_${index}`, "Other", `Other ${index}B`, options.scoreAt === index ? options.value : 90 - index);
    }
  };
}

function seedSizeClassScores(sizeClass: string, scores: readonly number[]) {
  return async (env: SubmissionApiEnv): Promise<void> => {
    for (const [index, score] of scores.entries()) {
      await insertBoardEntry(env, `size_${index}`, "Other", `Other ${sizeClass} Q4`, score);
    }
  };
}

function seedFamilyScores(family: string, scores: readonly number[]) {
  return async (env: SubmissionApiEnv): Promise<void> => {
    for (const [index, score] of scores.entries()) {
      await insertBoardEntry(env, `family_${index}`, family, `${family} 7B`, score);
    }
  };
}

async function insertBoardEntry(
  env: SubmissionApiEnv,
  id: string,
  family: string,
  displayName: string,
  score: number,
): Promise<void> {
  await env.DB.prepare("create table if not exists submissions_contract_v1 (submission_id text primary key)")
    .run();
  await env.DB.prepare("insert or ignore into submissions_contract_v1 (submission_id) values (?)")
    .bind(id)
    .run();
  await env.DB.prepare(
    `insert into board_entries (
      entry_id, submission_id, board_schema_version, visibility, origin, trust_label, verification_level,
      model_display_name, model_family, suite_release_id, suite_manifest_sha256, scorecard_id,
      coverage_profile_id, headline_complete, headline_score, partial_composite, measured_headline_weight,
      missing_headline_weight, known_headline_contribution, rank_scope, axis_scores_json, bench_scores_json,
      conformance_json, n_scored, n_errors, warning_count, projection_sha256, bundle_sha256
    ) values (?, ?, 'localbench.board_entries.v1', 'public', 'community', 'community_re_scored', 'bundle_rescored',
      ?, ?, 'suite-v1-full-exec-6axis-v1', ?, 'scorecard', 'full-exec-6axis-v1', 1, ?, ?, 1, 0, ?, 'full-exec-6axis-v1',
      '{}', '{}', '{}', 1, 0, 0, ?, ?)`,
  )
    .bind(id, id, displayName, family, "e".repeat(64), score, score, score, sha256Hex(`${id}:projection`), sha256Hex(`${id}:bundle`))
    .run();
}

async function seedAcceptedDecision(
  env: SubmissionApiEnv,
  submissionId: string,
  decision: "publishable" | "provisional" | "escalated",
  publishState: "preview" | "published" | "hidden" = "preview",
): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, ticket_id, status, status_reason, bundle_schema_version,
      raw_bundle_sha256, raw_bundle_size_bytes, suite_release_id, suite_manifest_sha256, projection_sha256,
      projection_r2_key, publish_state, uploaded_at, validated_at, idempotency_key, zt1_decision,
      zt1_decision_reason, zt1_decided_at, provisional_until, provisional_reason
    ) values (?, 'community', ?, ?, 'accepted', null, 'localbench.result_bundle.v1', ?, 100,
      'suite-v1-full-exec-6axis-v1', ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, datetime('now'),
      ?, ?)`,
  )
    .bind(
      submissionId,
      `public_key:${submissionId}`,
      submissionId,
      sha256Hex(`${submissionId}:raw`),
      "f".repeat(64),
      PROJECTION_SHA,
      `projections/${submissionId}/${PROJECTION_SHA}.json`,
      publishState,
      sha256Hex(`${submissionId}:raw`),
      decision,
      decision,
      decision === "provisional" ? new Date(Date.now() + 60 * 60 * 1000).toISOString() : null,
      decision === "provisional" ? "top_10_overall" : null,
    )
    .run();
}

async function seedRejected(env: SubmissionApiEnv, submissionId: string, reason: string): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, ticket_id, status, status_reason, bundle_schema_version,
      raw_bundle_sha256, suite_release_id, suite_manifest_sha256, publish_state, validated_at, idempotency_key
    ) values (?, 'community', ?, ?, 'rejected', ?, 'localbench.result_bundle.v1', ?, 'suite-v1-full-exec-6axis-v1', ?, 'hidden', datetime('now'), ?)`,
  )
    .bind(submissionId, `public_key:${submissionId}`, submissionId, reason, sha256Hex(`${submissionId}:raw`), "f".repeat(64), sha256Hex(`${submissionId}:raw`))
    .run();
}

async function seedPending(env: SubmissionApiEnv, count: number): Promise<void> {
  for (let index = 0; index < count; index += 1) {
    await seedStatusRow(env, `pending_${index}`, "pending_verification");
  }
}

async function seedRecentSubmissions(env: SubmissionApiEnv, count: number): Promise<void> {
  for (let index = 0; index < count; index += 1) {
    await seedStatusRow(env, `recent_${index}`, "ticketed");
  }
}

async function seedIngress(env: SubmissionApiEnv, bytes: number): Promise<void> {
  await seedStatusRow(env, "ingress_1", "pending_verification", bytes);
}

async function seedAcceptedRows(env: SubmissionApiEnv, count: number): Promise<void> {
  for (let index = 0; index < count; index += 1) {
    await seedAcceptedDecision(env, `accepted_alarm_${index}`, "publishable");
  }
}

async function seedDecisionRows(env: SubmissionApiEnv, count: number, decision: string): Promise<void> {
  for (let index = 0; index < count; index += 1) {
    await seedAcceptedDecision(env, `${decision}_${index}`, "escalated");
  }
  await env.DB.prepare("update submissions set validated_at = datetime('now', '-2 days') where submission_id like ?")
    .bind(`${decision}_%`)
    .run();
}

async function seedFlaggedRow(env: SubmissionApiEnv, flag: string): Promise<void> {
  await seedStatusRow(env, "flagged_1", "accepted");
  await env.DB.prepare("update submissions set zt1_flags_json = ? where submission_id = 'flagged_1'")
    .bind(JSON.stringify([flag]))
    .run();
}

async function seedStatusRow(
  env: SubmissionApiEnv,
  submissionId: string,
  status: string,
  rawBundleSizeBytes = 100,
): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, ticket_id, status, bundle_schema_version, raw_bundle_sha256,
      raw_bundle_size_bytes, suite_release_id, suite_manifest_sha256, publish_state, uploaded_at,
      validated_at, idempotency_key
    ) values (?, 'community', ?, ?, ?, 'localbench.result_bundle.v1', ?, ?, 'suite-v1-full-exec-6axis-v1', ?, 'hidden',
      datetime('now'), datetime('now'), ?)`,
  )
    .bind(submissionId, `public_key:${submissionId}`, submissionId, status, sha256Hex(`${submissionId}:raw`), rawBundleSizeBytes, "f".repeat(64), sha256Hex(`${submissionId}:raw`))
    .run();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

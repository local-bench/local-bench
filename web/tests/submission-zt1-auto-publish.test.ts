import { describe, expect, it } from "vitest";
import { handleApplyVerificationUpdate } from "../functions/_lib/submission-api";
import { handleAcceptedFeed } from "../functions/_lib/submission-feed-api";
import { canonicalJson } from "../functions/_lib/submission-canonical";
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
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  MIGRATION_0012,
  MIGRATION_0014,
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
import { testKeyPair } from "./submission-contract-v2-support";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";

const KNOWN_HASH = "a".repeat(64);
const UNKNOWN_HASH = "b".repeat(64);
const TRUSTED_ATTESTER = testKeyPair();
const ATTESTATION_SCHEMA = "localbench.verdict_attestation.v1";
const ATTESTATION_KEY_ID = "localbench-attester-test";

describe("ZT-1 automatic publish decisions", () => {
  it("marks low-impact accepted rows publishable when every auto-accept gate is green", async () => {
    // Given: auto-publish is enabled and the accepted bundle resolves to a trusted known catalog artifact.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({ fileSha: KNOWN_HASH, score: 62 }));

    // When: the verifier applies an accepted status update.
    const response = await verifyAccepted(env, submissionId);

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_identity_key: "qwen3-4b",
      identity_class: "known_artifact",
      publish_state: "published",
      zt1_decision: "publishable",
    });
    await expectDecisionLog(env, submissionId, "auto_accept", "publishable");
  }, 15_000);

  it("does not grant known artifact trust to an allowlisted hash without a trusted attestation", async () => {
    // Given: the bundle self-declares an allowlisted artifact hash but carries no trusted attestation.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      fileSha: KNOWN_HASH,
      score: 62,
      trustedAttestation: false,
    }));

    // When: the verifier accepts the submission.
    const response = await verifyAccepted(env, submissionId);

    // Then: ZT-1 treats the row as unverified instead of joining the trusted catalog slug.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_identity_key: KNOWN_HASH,
      identity_class: "unverified",
      provisional_reason: null,
      publish_state: "published",
      zt1_decision: "publishable",
    });
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
      zt1_decision_reason: "duplicate_artifact",
    });
  }, 15_000);

  it("keeps community verifier claims self-reported without holding publication", async () => {
    // Given: a COMMUNITY bundle self-declares verdict_source:"verifier" on all coding items. The
    // in-process coding sentinel is forgeable (docs/reports/coding-exec-framewalk-forgery-2026-07-07.md),
    // so a community "verifier" claim is self-reported and must not be auto-accepted. (origin is
    // server-assigned; issueEnvelope uses the admin secret => project_anchor, so force community here.)
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const bundle = bundleFor({ fileSha: UNKNOWN_HASH, score: 45 });
    bundle["items"] = [
      { bench: "bigcodebench_hard", item_id: "bcbh-001", code_artifact: { verdict_source: "verifier" } },
      { bench: "bigcodebench_hard", item_id: "bcbh-002", code_artifact: { verdict_source: "verifier" } },
    ];
    const submissionId = await ticketWithBundle(env, bundle);
    await env.DB.prepare("update submissions set origin = 'community' where submission_id = ?").bind(submissionId).run();

    // When: the verifier accepts the submission.
    const response = await verifyAccepted(env, submissionId);

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_coding_state: "self_reported_exec",
      zt1_decision: "publishable",
    });
  }, 15_000);

  it("consumes the current server-owned maintainer coding attestation on the real decision path", async () => {
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const receiptSha = "9".repeat(64);
    const bundle = bundleFor({ fileSha: UNKNOWN_HASH, score: 45 });
    bundle["receipt_references"] = { coding_receipt_sha256: receiptSha };
    bundle["items"] = [{ bench: "bigcodebench_hard", item_id: "bcbh-001", code_artifact: { verdict_source: "submitter" } }];
    const submissionId = await ticketWithBundle(env, bundle);
    await env.DB.prepare("update submissions set origin = 'community' where submission_id = ?").bind(submissionId).run();

    const response = await verifyAccepted(env, submissionId, {
      coding_receipt_sha256: receiptSha,
      decision: "verified",
      maintainer_key_id: "maintainer-release-key-1",
    });

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).not.toMatchObject({ zt1_decision_reason: "coding_self_reported_exec" });
    expect(body).toMatchObject({ zt1_coding_state: "verifier" });
    const record = await env.DB.prepare(
      "select raw_bundle_sha256, projection_object_sha256, coding_receipt_sha256, suite_release_id, suite_manifest_sha256, maintainer_key_id, decision, revision from maintainer_verification_attestations where submission_id = ?",
    ).bind(submissionId).first();
    expect(record).toMatchObject({ coding_receipt_sha256: receiptSha, decision: "verified", maintainer_key_id: "maintainer-release-key-1", revision: 1 });
  }, 15_000);

  it("still honors a project_anchor submission's verifier coding (gate is targeted)", async () => {
    // Contrast: the same all-"verifier" coding from an admin-authenticated project_anchor origin
    // stays trusted — the gate downgrades only community/self-reported verifier claims, it does not
    // break the maintainer path.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const bundle = bundleFor({ fileSha: UNKNOWN_HASH, score: 45 });
    bundle["items"] = [
      { bench: "bigcodebench_hard", item_id: "bcbh-001", code_artifact: { verdict_source: "verifier" } },
      { bench: "bigcodebench_hard", item_id: "bcbh-002", code_artifact: { verdict_source: "verifier" } },
    ];
    const submissionId = await ticketWithBundle(env, bundle);
    await env.DB.prepare("update submissions set origin = 'project_anchor' where submission_id = ?").bind(submissionId).run();

    const response = await verifyAccepted(env, submissionId);

    // Not escalated FOR CODING — the verifier state is honored for a project_anchor origin.
    expect(response.status).toBe(200);
    const body = (await response.json()) as Record<string, unknown>;
    expect(body["zt1_decision_reason"]).not.toBe("coding_self_reported_exec");
  }, 15_000);

  it("keeps empty community coding evidence pending without holding publication", async () => {
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const bundle = bundleFor({ fileSha: UNKNOWN_HASH, score: 45 });
    bundle["items"] = [
      { bench: "bigcodebench_hard", item_id: "bcbh-001", correct: true, code_artifact: {} },
      { bench: "bigcodebench_hard", item_id: "bcbh-002", correct: true, code_artifact: {} },
    ];
    const submissionId = await ticketWithBundle(env, bundle);
    await env.DB.prepare("update submissions set origin = 'community' where submission_id = ?").bind(submissionId).run();

    const response = await verifyAccepted(env, submissionId);

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_coding_state: "self_reported_exec",
      zt1_decision: "publishable",
    });
  }, 15_000);

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

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_display_label: "community-declared · identity unverified · Ava Bench",
      board_identity_key: UNKNOWN_HASH,
      identity_class: "unverified",
      provisional_reason: null,
      publish_state: "published",
      zt1_decision: "publishable",
    });
  }, 15_000);

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
  }, 15_000);

  it("does not escalate a fine-tune whose FAMILY fingerprint matches a protected pattern", async () => {
    // Given: an innocuously named fine-tune that legitimately declares a
    // protected base family (the core publish-then-moderate submission case).
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "bonsai-27b-ternary",
      family: "Qwen3",
      fileSha: UNKNOWN_HASH,
      score: 58,
    }));

    // When: verification accepts the bundle.
    const response = await verifyAccepted(env, submissionId);

    // Then: family membership alone never trips the impersonation hold.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_decision: "publishable",
    });
  }, 15_000);

  it("escalates protected identities from verified submitter keys", async () => {
    // Given: a verified submitter key is mapped to a protected vendor identity.
    const env = await createZt1Env();
    const protectedKey = testKeyPair();
    Object.assign(env, {
      ZT1_PROTECTED_KEYS_JSON: JSON.stringify({ [protectedKey.publicKeyHex]: "protected-vendor" }),
    });
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "Community Small",
      family: "Community",
      fileSha: UNKNOWN_HASH,
      score: 58,
    }));
    await env.DB.prepare("update submissions set submitter_id = ? where submission_id = ?")
      .bind(`public_key:${protectedKey.publicKeyHex}`, submissionId)
      .run();

    // When: verification accepts the bundle.
    const response = await verifyAccepted(env, submissionId);

    // Then: the non-forgeable key map escalates the row even without a protected name claim.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      board_identity_key: "protected-vendor",
      identity_class: "protected",
      publish_state: "hidden",
      zt1_decision_reason: "protected_identity",
    });
  }, 15_000);

  it("publishes self-reported agentic rows with a visible trust flag", async () => {
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

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      provisional_reason: null,
      publish_state: "published",
      zt1_decision: "publishable",
      zt1_decision_reason: expect.stringContaining("self_reported_agentic"),
    });
  }, 15_000);

  it.each([
    ["top_10_overall", seedBoardScores(10, { scoreAt: 10, value: 50 })],
    ["top_3_size_class", seedSizeClassScores("7b", [70, 65, 60])],
    ["family_number_one", seedFamilyScores("BenchFam", [59])],
    ["beats_prior_number_one", seedBoardScores(1, { scoreAt: 1, value: 60 })],
    ["first_page_first_time_key", seedBoardScores(9, { scoreAt: 9, value: 50 })],
  ])("publishes %s high-impact rows with an audit flag", async (reason, seed) => {
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

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({
      provisional_reason: null,
      publish_state: "published",
      zt1_decision: "publishable",
      zt1_decision_reason: expect.stringContaining(reason),
    });
  }, 15_000);

  it("ignores partial-only public scores for headline impact flags", async () => {
    // Given: the public board has only a legacy partial composite on a retired scale.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    await insertPartialOnlyBoardEntry(env, "partial_only_1", "BenchFam", "BenchFam 7B", 50);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "BenchFam 7B Q4",
      family: "BenchFam",
      fileSha: KNOWN_HASH,
      fileSizeBytes: 7_000_000_000,
      score: 62,
    }));

    // When: the verifier accepts a headline-scored submission.
    const response = await verifyAccepted(env, submissionId);

    // Then: zt1 does not compare the headline score against the retired partial pool.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_decision: "publishable",
    });
  }, 15_000);

  it("ignores an arbitrarily high unranked community score in the ZT-1 reference population", async () => {
    const env = await createZt1Env();
    await enableAutoPublish(env);
    await seedBoardScores(10, { scoreAt: 10, value: 50 })(env);
    await insertCommunityBoardEntry(env, "community_million", 1_000_000);
    const submissionId = await ticketWithBundle(env, bundleFor({ fileSha: KNOWN_HASH, score: 55 }));

    const response = await verifyAccepted(env, submissionId);

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_decision_reason: expect.stringContaining("top_10_overall"),
    });
  }, 15_000);

  it("publishes a new eligible decision even when the retired preview lane is full", async () => {
    // Given: the incoming provisional preview lane is already at capacity.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    for (let index = 0; index < 50; index += 1) {
      await seedAcceptedDecision(env, `provisional_cap_${index}`, "provisional");
    }
    await env.DB.prepare("update submissions set created_at = datetime('now', '-2 days'), validated_at = datetime('now', '-2 days') where submission_id like 'provisional_cap_%'")
      .run();
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "Community Tiny Q4",
      fileSha: UNKNOWN_HASH,
      score: 55,
    }));

    // When: another accepted row receives a provisional ZT-1 decision.
    const response = await verifyAccepted(env, submissionId);

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      publish_state: "published",
      zt1_decision: "publishable",
      zt1_decision_reason: expect.stringContaining("unknown_identity"),
    });
    const preview = await env.DB.prepare("select count(*) as count from submissions where publish_state = 'preview' and zt1_decision = 'provisional'").first();
    expect(preview).toMatchObject({ count: 50 });
  }, 15_000);

  it("writes a sybil pattern flag when one identity repeats in the recent window", async () => {
    // Given: the same trusted board identity already has several recent accepted rows.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    for (let index = 0; index < 3; index += 1) {
      await seedAcceptedDecision(env, `repeat_identity_${index}`, "publishable");
    }
    await env.DB.prepare("update submissions set board_identity_key = 'qwen3-4b' where submission_id like 'repeat_identity_%'")
      .run();
    const submissionId = await ticketWithBundle(env, bundleFor({ fileSha: KNOWN_HASH, score: 52 }));

    // When: ZT-1 persists the next decision for that identity.
    const response = await verifyAccepted(env, submissionId);

    // Then: the dead sybil freeze-alarm signal becomes reachable through zt1_flags_json.
    expect(response.status).toBe(200);
    const row = await env.DB.prepare("select zt1_flags_json from submissions where submission_id = ?")
      .bind(submissionId)
      .first();
    expect(JSON.parse(String(row?.["zt1_flags_json"]))).toContain("sybil_pattern");
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

  it("promotes at most one publishable row per identity in a batch", async () => {
    // Given: fifteen publishable preview rows all belong to one board identity.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    for (let index = 0; index < 15; index += 1) {
      await seedAcceptedDecision(env, `same_identity_${index}`, "publishable");
    }
    await env.DB.prepare(
      "update submissions set board_identity_key = 'shared-identity', validated_at = datetime('now', '-2 days') where submission_id like 'same_identity_%'",
    ).run();

    // When: the publish batch runs.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: only the oldest row from that identity is promoted.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.promoted).toEqual([{ submission_id: "same_identity_0" }]);
    const published = await env.DB.prepare("select count(*) as count from submissions where publish_state = 'published'").first();
    expect(published).toMatchObject({ count: 1 });
  }, 15_000);

  it("promotes ten rows across distinct identities in a batch", async () => {
    // Given: fifteen publishable preview rows each have their own board identity.
    const env = await createZt1Env();
    await enableAutoPublish(env);
    for (let index = 0; index < 15; index += 1) {
      await seedAcceptedDecision(env, `distinct_identity_${index}`, "publishable");
    }
    await env.DB.prepare("update submissions set validated_at = datetime('now', '-2 days') where submission_id like 'distinct_identity_%'")
      .run();

    // When: the publish batch runs.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: the batch still fills the 10-row limit when identities are distinct.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.promoted).toHaveLength(10);
    const distinctPublished = await env.DB.prepare("select count(distinct board_identity_key) as count from submissions where publish_state = 'published'")
      .first();
    expect(distinctPublished).toMatchObject({ count: 10 });
  }, 15_000);

  it.each([
    ["oldest_pending_age_gt_6h", seedOldPending],
    ["reject_rate_24h_gt_50pct", seedRejectRate],
    ["upload_bytes_24h_gt_8gib", async (env: SubmissionApiEnv) => seedIngress(env, 8 * 1024 * 1024 * 1024 + 1)],
    ["accepts_24h_gt_200", async (env: SubmissionApiEnv) => seedAcceptedRows(env, 201)],
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

  it("auto-recovers a security disable after cooldown when alarms clear", async () => {
    // Given: security disabled auto-publish before the cooldown and no alarm is firing now.
    const env = await createZt1Env();
    await seedAcceptedDecision(env, "recoverable_1", "publishable");
    await env.DB.prepare("update submissions set validated_at = datetime('now', '-2 days') where submission_id = 'recoverable_1'")
      .run();
    await setAutoPublishDisabled(env, "security", "2000-01-01T00:00:00.000Z");

    // When: the batch starts.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: auto-publish is re-enabled and the ready row can promote.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      auto_publish: "on",
      promoted: [{ submission_id: "recoverable_1" }],
    });
    const setting = await env.DB.prepare("select value, disabled_by from ops_settings where key = 'auto_publish'").first();
    expect(setting).toEqual({ disabled_by: null, value: "on" });
  }, 15_000);

  it("keeps a security disable when cooldown expires but an alarm is still firing", async () => {
    // Given: security disabled auto-publish before the cooldown and an old pending row still breaches an alarm.
    const env = await createZt1Env();
    await seedOldPending(env);
    await setAutoPublishDisabled(env, "security", "2000-01-01T00:00:00.000Z");

    // When: the batch starts.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: the security disable remains sticky for the active anomaly and the clock is reset.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      alarms: [expect.objectContaining({ reason: "oldest_pending_age_gt_6h" })],
      auto_publish: "off",
      promoted: [],
    });
    const setting = await env.DB.prepare("select value, disabled_by, updated_at from ops_settings where key = 'auto_publish'").first();
    expect(setting?.["value"]).toBe("off");
    expect(setting?.["disabled_by"]).toBe("security");
    expect(setting?.["updated_at"]).not.toBe("2000-01-01T00:00:00.000Z");
  }, 15_000);

  it("keeps owner-disabled auto-publish disabled after the cooldown", async () => {
    // Given: the owner disabled auto-publish long before the cooldown.
    const env = await createZt1Env();
    await seedAcceptedDecision(env, "owner_sticky_1", "publishable");
    await env.DB.prepare("update submissions set validated_at = datetime('now', '-2 days') where submission_id = 'owner_sticky_1'")
      .run();
    await setAutoPublishDisabled(env, "owner", "2000-01-01T00:00:00.000Z");

    // When: the batch starts.
    const response = await handlePublishBatch(adminGet("/api/admin/publish-batch"), env);

    // Then: owner intent is still sticky and no row promotes.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ auto_publish: "off", promoted: [] });
    const setting = await env.DB.prepare("select value, disabled_by from ops_settings where key = 'auto_publish'").first();
    expect(setting).toEqual({ disabled_by: "owner", value: "off" });
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
    for (const migration of [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0007, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011]) {
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
    migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0007, MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012, MIGRATION_0014],
  });
  return Object.assign(env, {
    ZT1_KNOWN_ARTIFACTS_JSON: JSON.stringify({ [KNOWN_HASH]: "qwen3-4b" }),
    ZT1_PROTECTED_MODEL_PATTERNS_JSON: JSON.stringify(["qwen", "gemma", "llama", "deepseek", "mistral", "phi"]),
    ZT1_TRUSTED_ATTESTER_PUBKEYS_JSON: JSON.stringify([TRUSTED_ATTESTER.publicKeyHex]),
  });
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

async function verifyAccepted(
  env: SubmissionApiEnv,
  submissionId: string,
  maintainerAttestation?: { readonly coding_receipt_sha256: string; readonly decision: "verified" | "not_verified"; readonly maintainer_key_id: string },
): Promise<Response> {
  const row = await env.DB.prepare("select raw_bundle_sha256, origin from submissions where submission_id = ?")
    .bind(submissionId)
    .first();
  const rawBundleSha = row?.["raw_bundle_sha256"];
  if (typeof rawBundleSha !== "string") {
    throw new Error("submission fixture did not store raw bundle sha");
  }
  const origin = row?.["origin"] === "community" ? "community" : "project_anchor";
  const codingReceipt = maintainerAttestation?.coding_receipt_sha256 ?? null;
  return handleApplyVerificationUpdate(
    adminJson(`/api/admin/submissions/${submissionId}/verification`, {
      ...statusUpdate("accepted", rawBundleSha, origin, codingReceipt),
      ...(maintainerAttestation === undefined ? {} : { maintainer_attestation: maintainerAttestation }),
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
  readonly trustedAttestation?: boolean;
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
  if (options.trustedAttestation !== false) {
    bundle["attestations"] = [trustedAttestation()];
  }
  return bundle;
}

function trustedAttestation(): Record<string, unknown> {
  const verdict = { collateral_damage: false, success: true };
  const payload = {
    attested_at: "2026-07-04T00:00:00Z",
    bench: "mmlu_pro",
    key_id: ATTESTATION_KEY_ID,
    run_id: "zt1-test-run",
    schema: ATTESTATION_SCHEMA,
    task_id: "zt1-test-task",
    verdict,
    verdict_sha256: sha256Hex(canonicalJson(verdict)),
  };
  return {
    payload,
    payload_sha256: sha256Hex(canonicalJson(payload)),
    signature: {
      algorithm: "Ed25519",
      public_key: TRUSTED_ATTESTER.publicKeyHex,
      signature: TRUSTED_ATTESTER.signMessage(canonicalJson(payload)),
    },
  };
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
    ) values (?, ?, 'localbench.board_entries.v1', 'public', 'project_anchor', 'project_anchor', 'bundle_rescored',
      ?, ?, 'suite-v1-full-exec-6axis-v1', ?, 'scorecard', 'full-exec-6axis-v1', 1, ?, ?, 1, 0, ?, 'full-exec-6axis-v1',
      '{}', '{}', '{}', 1, 0, 0, ?, ?)`,
  )
    .bind(id, id, displayName, family, "e".repeat(64), score, score, score, sha256Hex(`${id}:projection`), sha256Hex(`${id}:bundle`))
    .run();
}

async function insertPartialOnlyBoardEntry(
  env: SubmissionApiEnv,
  id: string,
  family: string,
  displayName: string,
  partialComposite: number,
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
      ?, ?, 'suite-v1-full-exec-6axis-v1', ?, 'scorecard', 'partial-exec-legacy', 0, null, ?, 0.5, 0.5, ?, 'partial-exec-legacy',
      '{}', '{}', '{}', 1, 0, 0, ?, ?)`,
  )
    .bind(
      id,
      id,
      displayName,
      family,
      "e".repeat(64),
      partialComposite,
      partialComposite,
      sha256Hex(`${id}:projection`),
      sha256Hex(`${id}:bundle`),
    )
    .run();
}

async function insertCommunityBoardEntry(env: SubmissionApiEnv, id: string, score: number): Promise<void> {
  await insertBoardEntry(env, id, "Adversary", "Adversary 1B", score);
  await env.DB.prepare("update board_entries set origin = 'community', trust_label = 'community_self_submitted' where entry_id = ?")
    .bind(id).run();
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
      zt1_decision_reason, zt1_decided_at, provisional_until, provisional_reason, identity_class,
      board_identity_key, board_display_label
    ) values (?, 'community', ?, ?, 'accepted', null, 'localbench.result_bundle.v1', ?, 100,
      'suite-v1-full-exec-6axis-v1', ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, datetime('now'),
      ?, ?, 'known_artifact', ?, ?)`,
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
      submissionId,
      `Label ${submissionId}`,
    )
    .run();
}

async function setAutoPublishDisabled(env: SubmissionApiEnv, disabledBy: "owner" | "security", updatedAt: string): Promise<void> {
  await env.DB.prepare(
    `insert into ops_settings (key, value, disabled_by, updated_at)
     values ('auto_publish', 'off', ?, ?)
     on conflict(key) do update set value = 'off', disabled_by = excluded.disabled_by, updated_at = excluded.updated_at`,
  )
    .bind(disabledBy, updatedAt)
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

async function seedOldPending(env: SubmissionApiEnv): Promise<void> {
  await seedPending(env, 1);
  await env.DB.prepare("update submissions set uploaded_at = datetime('now', '-7 hours') where submission_id = 'pending_0'")
    .run();
}

async function seedRejectRate(env: SubmissionApiEnv): Promise<void> {
  for (let index = 0; index < 20; index += 1) {
    await seedRejected(env, `reject_alarm_${index}`, "schema_violation");
  }
  await seedAcceptedRows(env, 10);
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
  await env.DB.prepare(
    `with recursive n(x) as (select 1 union all select x + 1 from n where x < ?)
     insert into submissions (
       submission_id, origin, status, raw_bundle_sha256, idempotency_key,
       publish_state, validated_at, zt1_decision
     ) select
       'accepted_alarm_' || x, 'community', 'accepted', printf('%064x', x + 900000),
       printf('%064x', x + 900000), 'preview', datetime('now'), 'publishable'
     from n`,
  ).bind(count).run();
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


describe("zt1 escalation resolve path", () => {
  it("maintainer resolve publishes a held row and is not repeatable", async () => {
    const { handleZt1Resolve } = await import("../functions/_lib/submission-zt1-resolve-api");
    const env = await createZt1Env();
    await enableAutoPublish(env);
    const submissionId = await ticketWithBundle(env, bundleFor({
      displayName: "Qwen3 4B Official",
      family: "Qwen3",
      fileSha: UNKNOWN_HASH,
      score: 58,
    }));
    const accepted = await verifyAccepted(env, submissionId);
    expect(accepted.status).toBe(200);
    expect(await accepted.json()).toMatchObject({ zt1_decision: "escalated", publish_state: "hidden" });

    const resolve = await handleZt1Resolve(
      jsonRequest(`/api/admin/submissions/${submissionId}/zt1-resolve`, { reason: "identity reviewed - distinct artifact" }, { "x-localbench-admin-secret": ADMIN_SECRET }),
      env,
      { submissionId },
    );
    expect(resolve.status).toBe(200);
    expect(await resolve.json()).toMatchObject({ publish_state: "published" });

    const again = await handleZt1Resolve(
      jsonRequest(`/api/admin/submissions/${submissionId}/zt1-resolve`, { reason: "repeat" }, { "x-localbench-admin-secret": ADMIN_SECRET }),
      env,
      { submissionId },
    );
    expect(again.status).toBe(409);
    expect(await again.json()).toMatchObject({ code: "not_escalated" });
  }, 20_000);
});

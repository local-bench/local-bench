import { describe, expect, it } from "vitest";
import { onRequestPost as applyVerification } from "../functions/api/admin/submissions/[submissionId]/verification";
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
  MIGRATION_0013,
  MIGRATION_0014,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  TEST_COMMUNITY_GROUP_ID,
  createEnv,
  jsonRequest,
  statusUpdate,
} from "./submission-test-support";

const GIB = 1024 * 1024 * 1024;

describe("automated-lane freeze alarms", () => {
  it.each([
    ["oldest_pending_age_gt_6h", seedOldPending],
    ["reject_rate_24h_gt_50pct", seedRejectRate],
    ["upload_bytes_24h_gt_8gib", seedUploadBytes],
    ["accepts_24h_gt_200", seedAcceptVolume],
  ] as const)("trips %s, disables auto-publish, and records the decision", async (reason, seed) => {
    const env = await alarmEnv();
    await seed(env);
    await insertCandidate(env);
    const response = await applyVerification({
      env,
      params: { submissionId: "ticket_fixture_alarm_candidate" },
      request: jsonRequest(
        "/api/admin/submissions/ticket_fixture_alarm_candidate/verification?override=true",
        statusUpdate("accepted", RAW_BUNDLE_SHA, "community"),
        { "x-localbench-admin-secret": ADMIN_SECRET },
      ),
    });
    const setting = await env.DB.prepare("select value, disabled_by from ops_settings where key = 'auto_publish'").first();
    const log = await env.DB.prepare(
      "select actor, event, reason from submission_decision_log where event = 'alarm' order by id desc limit 1",
    ).first();
    const candidate = await env.DB.prepare(
      "select status, publish_state from submissions where submission_id = 'ticket_fixture_alarm_candidate'",
    ).first();
    expect(response.status).toBe(200);
    expect(candidate).toMatchObject({ publish_state: "hidden", status: "accepted" });
    expect(setting).toMatchObject({ disabled_by: "security", value: "off" });
    expect(log).toMatchObject({ actor: "security", event: "alarm", reason });
  });
});

async function alarmEnv() {
  const env = await createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
      MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014,
    ],
  });
  await env.DB.prepare("update ops_settings set value = 'on' where key = 'auto_publish'").run();
  return env;
}

type AlarmEnv = Awaited<ReturnType<typeof alarmEnv>>;

async function insertCandidate(env: AlarmEnv): Promise<void> {
  await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, status, raw_bundle_sha256, raw_bundle_r2_key,
      raw_bundle_size_bytes, idempotency_key, publish_state, uploaded_at,
      suite_release_id, suite_manifest_sha256, community_model_group_id
    ) values ('ticket_fixture_alarm_candidate', 'community', ?, 'pending_verification', ?, ?, ?, ?, 'hidden', datetime('now'), ?, ?, ?)`,
  ).bind(
    `public_key:${"a".repeat(64)}`, RAW_BUNDLE_SHA, `submissions/raw/${RAW_BUNDLE_SHA}.json`,
    RESULT_BUNDLE_JSON.length, RAW_BUNDLE_SHA, SUITE_RELEASE_ID, SUITE_MANIFEST_SHA,
    TEST_COMMUNITY_GROUP_ID,
  ).run();
}

async function seedOldPending(env: AlarmEnv): Promise<void> {
  await insertSynthetic(env, {
    count: 1,
    options: { uploadedAt: "datetime('now', '-7 hours')" },
    prefix: "old_pending",
    status: "pending_verification",
  });
}

async function seedRejectRate(env: AlarmEnv): Promise<void> {
  await insertSynthetic(env, { count: 20, options: { validatedAt: "datetime('now')" }, prefix: "reject", status: "rejected" });
  await insertSynthetic(env, { count: 10, options: { validatedAt: "datetime('now')" }, prefix: "accept", status: "accepted" });
}

async function seedUploadBytes(env: AlarmEnv): Promise<void> {
  await insertSynthetic(env, {
    count: 1,
    options: { rawBundleSizeBytes: 8 * GIB + 1, uploadedAt: "datetime('now')" },
    prefix: "upload",
    status: "pending_verification",
  });
}

async function seedAcceptVolume(env: AlarmEnv): Promise<void> {
  await insertSynthetic(env, {
    count: 201,
    options: { validatedAt: "datetime('now')" },
    prefix: "accept_volume",
    status: "accepted",
  });
}

type SyntheticOptions = {
  readonly rawBundleSizeBytes?: number;
  readonly uploadedAt?: string;
  readonly validatedAt?: string;
};

type SyntheticSeed = {
  readonly count: number;
  readonly options: SyntheticOptions;
  readonly prefix: string;
  readonly status: string;
};

async function insertSynthetic(
  env: AlarmEnv,
  seed: SyntheticSeed,
): Promise<void> {
  const uploadedAt = seed.options.uploadedAt ?? "null";
  const validatedAt = seed.options.validatedAt ?? "null";
  const rawSize = seed.options.rawBundleSizeBytes ?? 1;
  await env.DB.prepare(
    `with recursive n(x) as (select 1 union all select x + 1 from n where x < ?)
     insert into submissions (
       submission_id, origin, status, raw_bundle_sha256, raw_bundle_size_bytes,
       idempotency_key, publish_state, uploaded_at, validated_at
     ) select
       'ticket_fixture_${seed.prefix}_' || x, 'community', ?, printf('%064x', x + ?), ?,
       printf('%064x', x + ?), 'hidden', ${uploadedAt}, ${validatedAt}
     from n`,
  ).bind(seed.count, seed.status, prefixOffset(seed.prefix), rawSize, prefixOffset(seed.prefix)).run();
}

function prefixOffset(prefix: string): number {
  return [...prefix].reduce((total, character) => total + character.charCodeAt(0), 0) * 1000;
}

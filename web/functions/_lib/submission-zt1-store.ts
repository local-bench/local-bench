import { jsonResponse } from "./submission-api-support";
import type { SubmissionApiEnv, SubmissionRow } from "./submission-contracts";
import { publicSubmission, updatePublishState } from "./submission-store";
import type { Zt1DecisionPlan } from "./submission-zt1-decision";

export type FreezeAlarm = {
  readonly count: number;
  readonly reason: string;
  readonly threshold: number;
};

export type PublishBatchManifest = {
  readonly alarms: readonly FreezeAlarm[];
  readonly auto_publish: "off" | "on";
  readonly deploy_note: string;
  readonly limit: 10;
  readonly promoted: readonly { readonly submission_id: string }[];
  readonly skipped_provisional: readonly string[];
};

const GIB = 1024 * 1024 * 1024;
const DEPLOY_NOTE = "Rows are publishable in D1 only; board artifact regeneration and deploy remain scripts/publish-board.ps1.";
const SECURITY_DISABLE_COOLDOWN_HOURS = 6;
const MAX_ROWS_PER_IDENTITY_PER_BATCH = 1;
const MAX_PROVISIONAL_ROWS = 50;
const SYBIL_IDENTITY_SUBMISSIONS_24H = 3;

type AutoPublishSetting = {
  readonly disabledBy: string | null;
  readonly updatedAt: string;
  readonly value: string;
};

export async function zt1Available(env: SubmissionApiEnv): Promise<boolean> {
  try {
    await env.DB.prepare("select identity_class from submissions limit 0").all();
    return true;
  } catch (error) {
    if (schemaMissing(error)) {
      return false;
    }
    throw error;
  }
}

export async function autoPublishEnabled(env: SubmissionApiEnv): Promise<boolean> {
  const row = await env.DB.prepare("select value from ops_settings where key = 'auto_publish'").first();
  return row?.["value"] === "on";
}

export async function persistZt1Decision(
  env: SubmissionApiEnv,
  submissionId: string,
  plan: Zt1DecisionPlan,
): Promise<void> {
  const flagsJson = await zt1FlagsForDecision(env, submissionId, plan);
  const revisionRow = await env.DB.prepare("select state_revision, publish_state from submissions where submission_id = ?").bind(submissionId).first();
  const revision = numeric(revisionRow?.["state_revision"]);
  const currentPublishState = text(revisionRow?.["publish_state"]);
  const publishState = currentPublishState === "published" && plan.zt1Decision === "publishable"
    ? "published"
    : await publishStateForDecision(env, plan);
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for ZT-1 decisions");
  const results = await env.DB.batch([
    env.DB.prepare(
    `update submissions set
      identity_class = ?,
      board_identity_key = ?,
      board_display_label = ?,
      provisional_until = ?,
      provisional_reason = ?,
      zt1_decision = ?,
      zt1_decision_reason = ?,
      zt1_decided_at = datetime('now'),
      zt1_coding_state = ?,
      publish_state = ?,
      zt1_flags_json = ?,
      state_revision = state_revision + 1,
      status_reason = case when ? = 'escalated' then ? else status_reason end
     where submission_id = ? and state_revision = ?`,
  )
    .bind(
      plan.identityClass,
      plan.boardIdentityKey,
      plan.boardDisplayLabel,
      plan.provisionalUntil,
      plan.provisionalReason,
      plan.zt1Decision,
      plan.reason,
      plan.codingState,
      publishState,
      flagsJson,
      plan.zt1Decision,
      `escalated:${plan.reason}`,
      submissionId,
      revision,
    ),
    env.DB.prepare("update publication_control set publication_revision = publication_revision + 1, updated_at = datetime('now') where singleton = 1 and changes() = 1"),
  ]);
  if (results[0]?.meta?.changes !== 1) throw new Error("concurrent ZT-1 decision revision mismatch");
  await recordDecisionLog(env, {
    actor: "system",
    details: plan.details,
    event: plan.zt1Decision === "publishable" ? "auto_accept" : plan.zt1Decision,
    reason: plan.reason,
    submissionId,
  });
}

export async function publicSubmissionWithZt1(
  env: SubmissionApiEnv,
  row: SubmissionRow,
): Promise<Record<string, unknown>> {
  const base = publicSubmission(row);
  try {
    const zt1 = await env.DB.prepare(
      `select identity_class, board_identity_key, board_display_label, provisional_until,
        provisional_reason, zt1_decision, zt1_decision_reason, zt1_coding_state
       from submissions where submission_id = ?`,
    )
      .bind(row.submission_id)
      .first();
    if (zt1 === null) {
      return base;
    }
    return { ...base, ...zt1 };
  } catch (error) {
    if (schemaMissing(error)) {
      return base;
    }
    throw error;
  }
}

export async function evaluateFreezeAlarms(env: SubmissionApiEnv): Promise<readonly FreezeAlarm[]> {
  const alarms = await currentFreezeAlarms(env);
  if (alarms.length > 0) {
    await disableAutoPublishForSecurity(env);
    await Promise.all(alarms.map((alarm) => recordAlarm(env, alarm)));
  }
  return alarms;
}

export function securityDisableExpired(row: AutoPublishSetting, nowIso: string): boolean {
  if (row.disabledBy !== "security") {
    return false;
  }
  const disabledAt = Date.parse(row.updatedAt);
  const now = Date.parse(nowIso);
  if (!Number.isFinite(disabledAt) || !Number.isFinite(now)) {
    return false;
  }
  return now - disabledAt >= SECURITY_DISABLE_COOLDOWN_HOURS * 60 * 60 * 1000;
}

async function currentFreezeAlarms(env: SubmissionApiEnv): Promise<readonly FreezeAlarm[]> {
  if (!await zt1Available(env)) {
    return [];
  }
  const alarms = [
    await thresholdAlarm(
      env,
      "oldest_pending_age_gt_6h",
      "select count(*) from submissions where status = 'pending_verification' and coalesce(uploaded_at, created_at) < datetime('now', '-6 hours')",
      0,
    ),
    await rejectRateAlarm(env),
    await thresholdAlarm(
      env,
      "upload_bytes_24h_gt_8gib",
      "select coalesce(sum(raw_bundle_size_bytes), 0) from submissions where uploaded_at >= datetime('now', '-24 hours')",
      8 * GIB,
    ),
    await thresholdAlarm(
      env,
      "accepts_24h_gt_200",
      "select count(*) from submissions where status = 'accepted' and validated_at >= datetime('now', '-24 hours')",
      200,
    ),
  ].filter((alarm): alarm is FreezeAlarm => alarm !== null);
  return alarms;
}

async function rejectRateAlarm(env: SubmissionApiEnv): Promise<FreezeAlarm | null> {
  const row = await env.DB.prepare(
    `select
       sum(case when status = 'rejected' then 1 else 0 end) as rejects,
       sum(case when status = 'accepted' then 1 else 0 end) as accepts
     from submissions
     where status in ('accepted', 'rejected') and validated_at >= datetime('now', '-24 hours')`,
  ).first();
  const rejects = numeric(row?.["rejects"] ?? 0);
  const accepts = numeric(row?.["accepts"] ?? 0);
  return rejects >= 20 && rejects / (rejects + accepts) > 0.5
    ? { count: rejects, reason: "reject_rate_24h_gt_50pct", threshold: 20 }
    : null;
}

export async function publishBatch(env: SubmissionApiEnv): Promise<PublishBatchManifest> {
  const recoveredAlarms = await autoRecoverSecurityDisable(env);
  const alarms = recoveredAlarms ?? await evaluateFreezeAlarms(env);
  const autoPublish = await autoPublishEnabled(env) ? "on" : "off";
  const skippedProvisional = await provisionalSubmissionIds(env);
  if (autoPublish === "off" || alarms.length > 0) {
    return { alarms, auto_publish: autoPublish, deploy_note: DEPLOY_NOTE, limit: 10, promoted: [], skipped_provisional: skippedProvisional };
  }
  const rows = await env.DB.prepare(
    `select submission_id
     from (
       select
         submission_id,
         coalesce(zt1_decided_at, validated_at, created_at) as decision_order,
         row_number() over (
           partition by coalesce(board_identity_key, submission_id)
           order by coalesce(zt1_decided_at, validated_at, created_at) asc, submission_id asc
         ) as identity_rank
       from submissions
       where status = 'accepted'
         and publish_state = 'preview'
         and zt1_decision = 'publishable'
         and provisional_until is null
     )
     where identity_rank <= ?
     order by decision_order asc, submission_id asc
     limit 10`,
  )
    .bind(MAX_ROWS_PER_IDENTITY_PER_BATCH)
    .all();
  const promoted: { readonly submission_id: string }[] = [];
  for (const row of rows.results) {
    const submissionId = text(row["submission_id"]);
    await updatePublishState(env, submissionId, "published", "zt1 daily batch publish");
    await recordDecisionLog(env, {
      actor: "system",
      details: {},
      event: "batch_publish",
      reason: "published",
      submissionId,
    });
    promoted.push({ submission_id: submissionId });
  }
  return { alarms, auto_publish: autoPublish, deploy_note: DEPLOY_NOTE, limit: 10, promoted, skipped_provisional: skippedProvisional };
}

export async function digest(env: SubmissionApiEnv): Promise<Record<string, readonly Record<string, string | null>[]>> {
  return {
    accepts: await digestRows(env, "zt1_decision in ('publishable', 'provisional')", "zt1_decided_at", "zt1_decision_reason"),
    alarms: await alarmRows(env),
    escalations: await digestRows(env, "zt1_decision = 'escalated'", "zt1_decided_at", "zt1_decision_reason"),
    provisional_elapsed: await digestRows(env, "zt1_decision = 'provisional' and provisional_until <= datetime('now')", "provisional_until", "provisional_reason"),
    rejects: await digestRows(env, "status = 'rejected'", "validated_at", "status_reason"),
  };
}

export function zt1UnavailableResponse(): Response {
  return jsonResponse(503, { code: "zt1_unavailable", error: "ZT-1 migration has not been applied" });
}

async function thresholdAlarm(
  env: SubmissionApiEnv,
  reason: string,
  sql: string,
  threshold: number,
): Promise<FreezeAlarm | null> {
  const row = await env.DB.prepare(`select (${sql}) as count`).first();
  const count = numeric(row?.["count"]);
  return count > threshold ? { count, reason, threshold } : null;
}

async function provisionalSubmissionIds(env: SubmissionApiEnv): Promise<readonly string[]> {
  const rows = await env.DB.prepare(
    "select submission_id from submissions where status = 'accepted' and publish_state = 'preview' and zt1_decision = 'provisional' order by zt1_decided_at asc",
  ).all();
  return rows.results.map((row) => text(row["submission_id"]));
}

async function disableAutoPublishForSecurity(env: SubmissionApiEnv): Promise<void> {
  await env.DB.prepare(
    `insert into ops_settings (key, value, disabled_by, updated_at)
     values ('auto_publish', 'off', 'security', datetime('now'))
     on conflict(key) do update set
       value = 'off',
       disabled_by = case when ops_settings.disabled_by = 'owner' then 'owner' else 'security' end,
       updated_at = case when ops_settings.disabled_by = 'owner' then ops_settings.updated_at else datetime('now') end`,
  ).run();
}

async function autoRecoverSecurityDisable(env: SubmissionApiEnv): Promise<readonly FreezeAlarm[] | null> {
  const setting = await autoPublishSetting(env);
  if (!securityDisableExpired(setting, new Date().toISOString())) {
    return null;
  }
  const alarms = await currentFreezeAlarms(env);
  if (alarms.length > 0) {
    await disableAutoPublishForSecurity(env);
    await Promise.all(alarms.map((alarm) => recordAlarm(env, alarm)));
    return alarms;
  }
  await env.DB.prepare(
    `update ops_settings
     set value = 'on', disabled_by = null, updated_at = datetime('now')
     where key = 'auto_publish' and value = 'off' and disabled_by = 'security'`,
  ).run();
  return [];
}

async function autoPublishSetting(env: SubmissionApiEnv): Promise<AutoPublishSetting> {
  const row = await env.DB.prepare("select value, disabled_by, updated_at from ops_settings where key = 'auto_publish'").first();
  if (row === null) {
    return { disabledBy: null, updatedAt: new Date().toISOString(), value: "off" };
  }
  return {
    disabledBy: nullableText(row["disabled_by"]),
    updatedAt: text(row["updated_at"]),
    value: text(row["value"]),
  };
}

async function publishStateForDecision(env: SubmissionApiEnv, plan: Zt1DecisionPlan): Promise<"hidden" | "preview"> {
  if (plan.zt1Decision === "escalated") {
    return "hidden";
  }
  if (plan.zt1Decision === "publishable") {
    return "hidden";
  }
  const row = await env.DB.prepare(
    "select count(*) as count from submissions where publish_state = 'preview' and zt1_decision = 'provisional'",
  ).first();
  return numeric(row?.["count"]) >= MAX_PROVISIONAL_ROWS ? "hidden" : "preview";
}

async function zt1FlagsForDecision(env: SubmissionApiEnv, submissionId: string, plan: Zt1DecisionPlan): Promise<string> {
  const flags = new Set(await existingZt1Flags(env, submissionId));
  if (await repeatedIdentityInRecentWindow(env, submissionId, plan.boardIdentityKey)) {
    flags.add("sybil_pattern");
  }
  return JSON.stringify([...flags].sort());
}

async function existingZt1Flags(env: SubmissionApiEnv, submissionId: string): Promise<readonly string[]> {
  const row = await env.DB.prepare("select zt1_flags_json from submissions where submission_id = ?")
    .bind(submissionId)
    .first();
  const raw = nullableText(row?.["zt1_flags_json"]);
  if (raw === null) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch (error) {
    if (error instanceof SyntaxError) {
      return [];
    }
    throw error;
  }
}

async function repeatedIdentityInRecentWindow(env: SubmissionApiEnv, submissionId: string, boardIdentityKey: string): Promise<boolean> {
  const row = await env.DB.prepare(
    `select count(*) as count
     from submissions
     where submission_id <> ?
       and board_identity_key = ?
       and created_at >= datetime('now', '-24 hours')`,
  )
    .bind(submissionId, boardIdentityKey)
    .first();
  return numeric(row?.["count"]) >= SYBIL_IDENTITY_SUBMISSIONS_24H;
}

export async function resolveEscalatedDecision(
  env: SubmissionApiEnv,
  submissionId: string,
  reason: string,
): Promise<boolean> {
  const result = await env.DB.prepare(
    `update submissions
     set zt1_decision = 'publishable', zt1_decision_reason = null, state_revision = state_revision + 1
     where submission_id = ? and zt1_decision = 'escalated'`,
  )
    .bind(submissionId)
    .run();
  const changed = (result.meta?.changes ?? 0) > 0;
  if (changed) {
    await recordDecisionLog(env, {
      actor: "maintainer",
      details: {},
      event: "zt1_resolved",
      reason,
      submissionId,
    });
  }
  return changed;
}

async function recordAlarm(env: SubmissionApiEnv, alarm: FreezeAlarm): Promise<void> {
  await recordDecisionLog(env, {
    actor: "security",
    details: { count: alarm.count, threshold: alarm.threshold },
    event: "alarm",
    reason: alarm.reason,
    submissionId: null,
  });
}

async function recordDecisionLog(
  env: SubmissionApiEnv,
  entry: {
    readonly actor: string;
    readonly details: Record<string, string | number | boolean | null>;
    readonly event: string;
    readonly reason: string;
    readonly submissionId: string | null;
  },
): Promise<void> {
  await env.DB.prepare(
    "insert into submission_decision_log (submission_id, actor, event, reason, details_json) values (?, ?, ?, ?, ?)",
  )
    .bind(entry.submissionId, entry.actor, entry.event, entry.reason, JSON.stringify(entry.details))
    .run();
}

async function digestRows(
  env: SubmissionApiEnv,
  predicate: string,
  timeColumn: string,
  reasonColumn: string,
): Promise<readonly Record<string, string | null>[]> {
  const rows = await env.DB.prepare(
    `select submission_id, ${reasonColumn} as reason
     from submissions
     where ${predicate} and coalesce(${timeColumn}, created_at) >= datetime('now', '-24 hours')
     order by coalesce(${timeColumn}, created_at) desc`,
  ).all();
  return rows.results.map((row) => ({
    reason: nullableText(row["reason"]),
    submission_id: text(row["submission_id"]),
  }));
}

async function alarmRows(env: SubmissionApiEnv): Promise<readonly Record<string, string | null>[]> {
  const rows = await env.DB.prepare(
    "select reason from submission_decision_log where event = 'alarm' and created_at >= datetime('now', '-24 hours') order by created_at desc",
  ).all();
  return rows.results.map((row) => ({ reason: text(row["reason"]), submission_id: null }));
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new Error("expected text value");
  }
  return value;
}

function nullableText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numeric(value: unknown): number {
  if (typeof value !== "number") {
    throw new Error("expected numeric value");
  }
  return value;
}

function schemaMissing(error: unknown): boolean {
  return error instanceof Error && (
    error.message.includes("no such column") ||
    error.message.includes("no such table: submission_decision_log")
  );
}

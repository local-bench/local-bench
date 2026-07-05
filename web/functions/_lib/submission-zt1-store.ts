import { jsonResponse } from "./submission-api-support";
import type { SubmissionApiEnv, SubmissionRow } from "./submission-contracts";
import { publicSubmission, recordSubmissionTransition } from "./submission-store";
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
  const publishState = plan.zt1Decision === "escalated" ? "hidden" : "preview";
  await env.DB.prepare(
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
      status_reason = case when ? = 'escalated' then ? else status_reason end
     where submission_id = ?`,
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
      plan.zt1Decision,
      `escalated:${plan.reason}`,
      submissionId,
    )
    .run();
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
  if (!await zt1Available(env)) {
    return [];
  }
  const alarms = [
    await thresholdAlarm(env, "pending_gt_20", "select count(*) from submissions where status = 'pending_verification'", 20),
    await thresholdAlarm(env, "submissions_24h_gt_50", "select count(*) from submissions where created_at >= datetime('now', '-24 hours')", 50),
    await thresholdAlarm(env, "r2_ingress_24h_gt_2gib", "select coalesce(sum(raw_bundle_size_bytes), 0) from submissions where uploaded_at >= datetime('now', '-24 hours')", 2 * GIB),
    await thresholdAlarm(env, "escalations_24h_gt_10", "select count(*) from submissions where zt1_decision = 'escalated' and zt1_decided_at >= datetime('now', '-24 hours')", 10),
    await thresholdAlarm(env, "accepts_24h_gt_10", "select count(*) from submissions where status = 'accepted' and validated_at >= datetime('now', '-24 hours')", 10),
    await thresholdAlarm(env, "sybil_pattern_flag", "select count(*) from submissions where zt1_flags_json like '%sybil_pattern%'", 0),
  ].filter((alarm): alarm is FreezeAlarm => alarm !== null);
  if (alarms.length > 0) {
    await disableAutoPublishForSecurity(env);
    await Promise.all(alarms.map((alarm) => recordAlarm(env, alarm)));
  }
  return alarms;
}

export async function publishBatch(env: SubmissionApiEnv): Promise<PublishBatchManifest> {
  const alarms = await evaluateFreezeAlarms(env);
  const autoPublish = await autoPublishEnabled(env) ? "on" : "off";
  const skippedProvisional = await provisionalSubmissionIds(env);
  if (autoPublish === "off" || alarms.length > 0) {
    return { alarms, auto_publish: autoPublish, deploy_note: DEPLOY_NOTE, limit: 10, promoted: [], skipped_provisional: skippedProvisional };
  }
  const rows = await env.DB.prepare(
    `select submission_id
     from submissions
     where status = 'accepted'
       and publish_state = 'preview'
       and zt1_decision = 'publishable'
       and provisional_until is null
     order by coalesce(zt1_decided_at, validated_at, created_at) asc
     limit 10`,
  ).all();
  const promoted: { readonly submission_id: string }[] = [];
  for (const row of rows.results) {
    const submissionId = text(row["submission_id"]);
    await env.DB.prepare("update submissions set publish_state = 'published', published_at = datetime('now') where submission_id = ?")
      .bind(submissionId)
      .run();
    await recordSubmissionTransition(env, {
      actor: "maintainer",
      fromStatus: "accepted",
      publishState: "published",
      reason: "zt1 daily batch publish",
      submissionId,
      toStatus: "accepted",
    });
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
     on conflict(key) do update set value = 'off', disabled_by = 'security', updated_at = datetime('now')`,
  ).run();
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

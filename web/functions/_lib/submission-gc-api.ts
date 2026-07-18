import { GcRequestSchema, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, jsonResponse } from "./submission-api-support";
import { recordSubmissionTransition } from "./submission-store";

type GcRow = {
  readonly publish_state: string;
  readonly raw_bundle_sha256: string;
  readonly raw_bundle_r2_key: string | null;
  readonly status: string;
  readonly submission_id: string;
};

type GcBucket = {
  readonly count: number;
  readonly submission_ids: readonly string[];
};

export async function handleGcSubmissions(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  let body: unknown;
  try {
    body = await requestJsonOrEmptyObject(request);
  } catch {
    return jsonResponse(400, { code: "invalid_gc_request", error: "invalid garbage collection request" });
  }
  const parsed = GcRequestSchema.safeParse(body);
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_gc_request", error: "invalid garbage collection request" });
  }
  const plan = {
    acceptedRaw: await acceptedRawRows(env),
    expiredTickets: await expiredTicketRows(env),
    stalePending: await stalePendingRows(env),
    rejectedRaw: await rejectedRawRows(env),
  };
  if (parsed.data.apply) {
    await applyExpiredTickets(env, plan.expiredTickets);
    await applyStalePending(env, plan.stalePending);
    await applyRawDeletes(env, plan.rejectedRaw, "gc: rejected raw bundle deleted");
    await applyRawDeletes(env, plan.acceptedRaw, "gc: accepted raw bundle retention elapsed");
  }
  return jsonResponse(200, {
    accepted_raw_deleted: bucket(plan.acceptedRaw),
    apply: parsed.data.apply,
    expired_tickets: bucket(plan.expiredTickets),
    stale_pending_expired: bucket(plan.stalePending),
    rejected_raw_deleted: bucket(plan.rejectedRaw),
  });
}

async function stalePendingRows(env: SubmissionApiEnv): Promise<readonly GcRow[]> {
  return gcRows(
    await env.DB.prepare(
      `select submission_id, status, publish_state, raw_bundle_sha256, raw_bundle_r2_key
       from submissions
       where status = 'pending_verification'
         and uploaded_at is not null
         and uploaded_at < datetime('now', '-14 days')
       order by submission_id`,
    ).all(),
  );
}

async function requestJsonOrEmptyObject(request: Request): Promise<unknown> {
  const text = await request.text();
  if (text.trim().length === 0) {
    return {};
  }
  return JSON.parse(text);
}

async function expiredTicketRows(env: SubmissionApiEnv): Promise<readonly GcRow[]> {
  return gcRows(
    await env.DB.prepare(
      `select submission_id, status, publish_state, raw_bundle_sha256, raw_bundle_r2_key
       from submissions
       where status = 'ticketed'
         and uploaded_at is null
         and expires_at is not null
         and expires_at < datetime('now', '-24 hours')
       order by submission_id`,
    ).all(),
  );
}

async function rejectedRawRows(env: SubmissionApiEnv): Promise<readonly GcRow[]> {
  return gcRows(
    await env.DB.prepare(
      `select submission_id, status, publish_state, raw_bundle_sha256, raw_bundle_r2_key
       from submissions
       where status = 'rejected'
         and raw_bundle_r2_key is not null
         and validated_at is not null
         and validated_at < datetime('now', '-7 days')
       order by submission_id`,
    ).all(),
  );
}

async function acceptedRawRows(env: SubmissionApiEnv): Promise<readonly GcRow[]> {
  return gcRows(
    await env.DB.prepare(
      `select submission_id, status, publish_state, raw_bundle_sha256, raw_bundle_r2_key
       from submissions
       where status = 'accepted'
         and raw_bundle_r2_key is not null
         and uploaded_at is not null
         and uploaded_at < datetime('now', '-90 days')
       order by submission_id`,
    ).all(),
  );
}

async function applyExpiredTickets(env: SubmissionApiEnv, rows: readonly GcRow[]): Promise<void> {
  for (const row of rows) {
    await deleteRawBundleIfUnshared(env, row);
    await env.DB.prepare("update submissions set status = 'expired', publish_state = 'hidden', raw_bundle_r2_key = null where submission_id = ?")
      .bind(row.submission_id)
      .run();
    await recordSubmissionTransition(env, {
      actor: "gc",
      fromStatus: row.status,
      publishState: "hidden",
      reason: "gc: ticket expired without upload",
      submissionId: row.submission_id,
      toStatus: "expired",
    });
  }
}

async function applyStalePending(env: SubmissionApiEnv, rows: readonly GcRow[]): Promise<void> {
  for (const row of rows) {
    await deleteRawBundleIfUnshared(env, row);
    await env.DB.prepare(
      "update submissions set status = 'expired', status_reason = ?, publish_state = 'hidden', raw_bundle_r2_key = null where submission_id = ? and status = 'pending_verification'",
    )
      .bind("pending verification expired after 14 days", row.submission_id)
      .run();
    await recordSubmissionTransition(env, {
      actor: "gc",
      fromStatus: row.status,
      publishState: "hidden",
      reason: "gc: stale pending submission expired and raw bundle deleted",
      submissionId: row.submission_id,
      toStatus: "expired",
    });
  }
}

async function applyRawDeletes(env: SubmissionApiEnv, rows: readonly GcRow[], reason: string): Promise<void> {
  for (const row of rows) {
    await deleteRawBundleIfUnshared(env, row);
    await env.DB.prepare("update submissions set raw_bundle_r2_key = null where submission_id = ?")
      .bind(row.submission_id)
      .run();
    await recordSubmissionTransition(env, {
      actor: "gc",
      fromStatus: row.status,
      publishState: row.publish_state,
      reason,
      submissionId: row.submission_id,
      toStatus: row.status,
    });
  }
}

function bucket(rows: readonly GcRow[]): GcBucket {
  return {
    count: rows.length,
    submission_ids: rows.map((row) => row.submission_id),
  };
}

function gcRows(rows: { readonly results: readonly Record<string, unknown>[] }): readonly GcRow[] {
  return rows.results.map((row) => ({
    publish_state: text(row, "publish_state"),
    raw_bundle_sha256: text(row, "raw_bundle_sha256"),
    raw_bundle_r2_key: nullableText(row, "raw_bundle_r2_key"),
    status: text(row, "status"),
    submission_id: text(row, "submission_id"),
  }));
}

async function deleteRawBundleIfUnshared(env: SubmissionApiEnv, row: GcRow): Promise<void> {
  if (row.raw_bundle_r2_key === null) return;
  const shared = await env.DB.prepare(
    `select 1 as referenced from submissions
     where submission_id <> ? and raw_bundle_sha256 = ?
       and status not in ('rejected', 'expired', 'withdrawn', 'suppressed', 'superseded')
     limit 1`,
  ).bind(row.submission_id, row.raw_bundle_sha256).first();
  if (shared === null) await env.SUBMISSIONS.delete(row.raw_bundle_r2_key);
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") {
    throw new Error(`gc row ${key} must be a string`);
  }
  return value;
}

function nullableText(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value === null || typeof value === "string") {
    return value;
  }
  throw new Error(`gc row ${key} must be a string or null`);
}

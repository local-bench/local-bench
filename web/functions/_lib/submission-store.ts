import {
  RESULT_BUNDLE_SCHEMA_VERSION,
  SubmissionRowSchema,
  type SubmissionApiEnv,
  type SubmissionEnvelope,
  type SubmissionRow,
} from "./submission-contracts";
import { sha256Hex } from "./submission-canonical";
import { InvalidTransitionError, assertTransition, type SubmissionStatus } from "./submission-state";
import { rawBundleKey } from "./submission-storage";

export type TransitionActor = "system" | "maintainer" | "auto-validator" | "gc";

export type TransitionRecord = {
  readonly actor: TransitionActor;
  readonly fromStatus: string | null;
  readonly publishState: "hidden" | "preview" | "published" | string | null;
  readonly reason?: string | null;
  readonly submissionId: string;
  readonly toStatus: string;
};

export type PublicTransitionHistory = {
  readonly actor: string;
  readonly created_at: string;
  readonly reason?: string;
  readonly to_status: string;
};

export type AcceptedFeedRow = {
  readonly origin: string;
  readonly publish_state: string;
  readonly raw_bundle_sha256: string;
  readonly submission_id: string;
  readonly submitter_display_name: string | null;
  readonly suite_release_id: string | null;
  readonly validated_at: string | null;
};

export type PendingQueueRow = {
  readonly declared_model_slug: string | null;
  readonly queued_at: string;
  readonly submission_id: string;
  readonly suite_release_id: string | null;
};

export type PendingQueueResult = {
  readonly rows: readonly PendingQueueRow[];
  readonly totalPending: number;
};

export const PENDING_VERIFICATION_GLOBAL_LIMIT = 200;
export const PENDING_VERIFICATION_PER_SUBMITTER_LIMIT = 10;

export type PendingAdmissionResult =
  | { readonly kind: "ok" }
  | { readonly kind: "error"; readonly code: "global_pending_limit" | "pending_review_limit" | "submission_not_ticketed" };

export async function insertTicketedSubmission(env: SubmissionApiEnv, ticket: SubmissionEnvelope): Promise<void> {
  const uploadCapabilitySha256 = await sha256Hex(ticket.upload_capability);
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, submitter_display_name, declared_model_slug, ticket_id, status, bundle_schema_version,
      raw_bundle_sha256, raw_bundle_r2_key, suite_release_id, suite_manifest_sha256, expires_at, idempotency_key,
      upload_capability_sha256, community_model_group_id
    ) values (?, ?, ?, ?, ?, ?, 'ticketed', ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      ticket.ticket_id,
      ticket.origin,
      ticket.submitter_id,
      ticket.submitter_display_name ?? null,
      ticket.declared_model_slug ?? null,
      ticket.ticket_id,
      RESULT_BUNDLE_SCHEMA_VERSION,
      ticket.bundle_sha256,
      rawBundleKey(ticket.bundle_sha256),
      ticket.expected_suite_release_id,
      ticket.expected_suite_manifest_sha256,
      ticket.expires_at,
      ticket.bundle_sha256,
      uploadCapabilitySha256,
      ticket.community_model_group_id ?? null,
    )
    .run();
  await recordSubmissionTransition(env, {
    actor: "system",
    fromStatus: null,
    publishState: "hidden",
    reason: "ticket issued",
    submissionId: ticket.ticket_id,
    toStatus: "ticketed",
  });
}

export async function rotateTicketedSubmission(env: SubmissionApiEnv, currentSubmissionId: string, ticket: SubmissionEnvelope): Promise<void> {
  const uploadCapabilitySha256 = await sha256Hex(ticket.upload_capability);
  await env.DB.prepare(
    `update submissions set
      submission_id = ?, ticket_id = ?, submitter_id = ?, submitter_display_name = ?, declared_model_slug = ?, origin = ?, suite_release_id = ?,
      suite_manifest_sha256 = ?, expires_at = ?, bundle_schema_version = ?, upload_capability_sha256 = ?, community_model_group_id = ?
      where submission_id = ?`,
  )
    .bind(
      ticket.ticket_id,
      ticket.ticket_id,
      ticket.submitter_id,
      ticket.submitter_display_name ?? null,
      ticket.declared_model_slug ?? null,
      ticket.origin,
      ticket.expected_suite_release_id,
      ticket.expected_suite_manifest_sha256,
      ticket.expires_at,
      RESULT_BUNDLE_SCHEMA_VERSION,
      uploadCapabilitySha256,
      ticket.community_model_group_id ?? null,
      currentSubmissionId,
    )
    .run();
}

export async function markPendingVerification(
  env: SubmissionApiEnv,
  submissionId: string,
  sizeBytes: number,
): Promise<PendingAdmissionResult> {
  const current = await requiredRow(env, submissionId);
  assertTransition(current.status, "pending_verification");
  const update = await env.DB.prepare(
    `update submissions set
      uploaded_at = datetime('now'), status = 'pending_verification', raw_bundle_size_bytes = ?,
      upload_capability_sha256 = null
      where submission_id = ? and status = 'ticketed' and uploaded_at is null
        and (select count(*) from submissions where submitter_id = ? and status = 'pending_verification') < ?
        and (select count(*) from submissions where status = 'pending_verification') < ?`,
  )
    .bind(
      sizeBytes,
      submissionId,
      current.submitter_id,
      PENDING_VERIFICATION_PER_SUBMITTER_LIMIT,
      PENDING_VERIFICATION_GLOBAL_LIMIT,
    )
    .run();
  if (update.meta?.changes === 0) {
    return diagnosePendingAdmissionFailure(env, current);
  }
  await recordSubmissionTransition(env, {
    actor: "system",
    fromStatus: current.status,
    publishState: current.publish_state,
    reason: "upload completed",
    submissionId,
    toStatus: "pending_verification",
  });
  return { kind: "ok" };
}

async function diagnosePendingAdmissionFailure(
  env: SubmissionApiEnv,
  current: SubmissionRow,
): Promise<PendingAdmissionResult> {
  const refreshed = await rowBySubmissionId(env, current.submission_id);
  if (refreshed === null || refreshed.status !== "ticketed" || refreshed.uploaded_at !== null) {
    return { code: "submission_not_ticketed", kind: "error" };
  }
  if (current.submitter_id !== null && await countPendingVerificationForSubmitter(env, current.submitter_id) >= PENDING_VERIFICATION_PER_SUBMITTER_LIMIT) {
    return { code: "pending_review_limit", kind: "error" };
  }
  if (await countPendingVerification(env) >= PENDING_VERIFICATION_GLOBAL_LIMIT) {
    return { code: "global_pending_limit", kind: "error" };
  }
  return { code: "submission_not_ticketed", kind: "error" };
}

export async function updatePublishState(
  env: SubmissionApiEnv,
  submissionId: string,
  publishState: "hidden" | "preview" | "published",
  reason: string | null = null,
): Promise<void> {
  const current = await requiredRow(env, submissionId);
  if (current.status !== "accepted") {
    throw new InvalidTransitionError(current.status, `publish_state:${publishState}`);
  }
  if (current.publish_state === publishState) return;
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for publication changes");
  const results = await env.DB.batch([
    env.DB.prepare(
      `update submissions set publish_state = ?, published_at = case when ? = 'published' then datetime('now') else published_at end,
       state_revision = state_revision + 1 where submission_id = ? and status = 'accepted' and state_revision = ?`,
    ).bind(publishState, publishState, submissionId, current.state_revision),
    env.DB.prepare("update publication_control set publication_revision = publication_revision + 1, updated_at = datetime('now') where singleton = 1 and changes() = 1"),
    env.DB.prepare(
      `insert into submission_transitions (submission_id, from_status, to_status, publish_state, actor, reason, state_revision)
       select ?, ?, ?, ?, 'maintainer', ?, ? where changes() = 1`,
    ).bind(submissionId, current.status, current.status, publishState, reason, current.state_revision + 1),
  ]);
  if (results[0]?.meta?.changes !== 1) throw new InvalidTransitionError(current.status, `publish_state:${publishState}`);
}

export async function transitionAcceptedToTerminal(
  env: SubmissionApiEnv,
  submissionId: string,
  toStatus: "withdrawn" | "suppressed",
  reason: string,
): Promise<void> {
  const current = await requiredRow(env, submissionId);
  assertTransition(current.status, toStatus);
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for suppression");
  const results = await env.DB.batch([
    env.DB.prepare(
      "update submissions set status = ?, status_reason = ?, publish_state = 'hidden', state_revision = state_revision + 1 where submission_id = ? and status = 'accepted' and state_revision = ?",
    ).bind(toStatus, reason, submissionId, current.state_revision),
    env.DB.prepare(
      `update publication_control set
         publication_revision = publication_revision + 1,
         edge_block_revision = edge_block_revision + 1,
         active_snapshot_id = case when exists (
           select 1 from publication_snapshot_rows r
           where r.snapshot_id = publication_control.active_snapshot_id and r.submission_id = ?
         ) then null else active_snapshot_id end,
         updated_at = datetime('now')
       where singleton = 1 and changes() = 1`,
    ).bind(submissionId),
    env.DB.prepare(
      `insert into publication_edge_blocks (submission_id, reason, publication_revision)
       select ?, ?, publication_revision from publication_control where singleton = 1 and changes() = 1
       on conflict(submission_id) do update set blocked_at = datetime('now'), reason = excluded.reason, publication_revision = excluded.publication_revision`,
    ).bind(submissionId, reason),
    env.DB.prepare(
      `insert into submission_transitions (submission_id, from_status, to_status, publish_state, actor, reason, state_revision)
       select ?, ?, ?, 'hidden', 'maintainer', ?, ? where changes() = 1`,
    ).bind(submissionId, current.status, toStatus, reason, current.state_revision + 1),
  ]);
  if (results[0]?.meta?.changes !== 1) throw new InvalidTransitionError(current.status, toStatus);
}

export async function rowBySubmissionId(env: SubmissionApiEnv, submissionId: string): Promise<SubmissionRow | null> {
  return parseRow(
    await env.DB.prepare(rowSelectSql("submission_id"))
      .bind(submissionId)
      .first(),
  );
}

export async function rowByRawBundleSha(env: SubmissionApiEnv, rawBundleSha256: string): Promise<SubmissionRow | null> {
  return parseRow(
    await env.DB.prepare(rowSelectSql("raw_bundle_sha256"))
      .bind(rawBundleSha256)
      .first(),
  );
}

export async function countPendingVerificationForSubmitter(env: SubmissionApiEnv, submitterId: string): Promise<number> {
  const row = await env.DB.prepare(
    "select count(*) as count from submissions where submitter_id = ? and status = 'pending_verification'",
  )
    .bind(submitterId)
    .first();
  const count = row?.["count"];
  return typeof count === "number" ? count : 0;
}

export async function countPendingVerification(env: SubmissionApiEnv): Promise<number> {
  const row = await env.DB.prepare(
    "select count(*) as count from submissions where status = 'pending_verification'",
  ).first();
  const count = row?.["count"];
  return typeof count === "number" ? count : 0;
}

export async function listPendingVerificationQueue(
  env: SubmissionApiEnv,
  limit: number,
): Promise<PendingQueueResult> {
  const rows = await env.DB.prepare(
    `select submission_id, declared_model_slug, suite_release_id,
            coalesce(uploaded_at, created_at) as queued_at,
            count(*) over () as total_pending
     from submissions
     where status = 'pending_verification'
     order by coalesce(uploaded_at, created_at) asc, created_at asc, submission_id asc
     limit ?`,
  )
    .bind(limit)
    .all();
  const mapped = rows.results.map((row) => ({
    declared_model_slug: nullableText(row, "declared_model_slug"),
    queued_at: text(row, "queued_at"),
    submission_id: text(row, "submission_id"),
    suite_release_id: nullableText(row, "suite_release_id"),
  }));
  const total = rows.results[0]?.["total_pending"];
  return { rows: mapped, totalPending: typeof total === "number" ? total : 0 };
}

export async function pendingVerificationPosition(
  env: SubmissionApiEnv,
  submissionId: string,
): Promise<{ readonly position: number; readonly totalPending: number } | null> {
  const row = await env.DB.prepare(
    `select position, total_pending from (
       select submission_id,
              row_number() over (order by coalesce(uploaded_at, created_at) asc, created_at asc, submission_id asc) as position,
              count(*) over () as total_pending
       from submissions where status = 'pending_verification'
     ) where submission_id = ?`,
  ).bind(submissionId).first();
  const position = row?.["position"];
  const totalPending = row?.["total_pending"];
  return typeof position === "number" && typeof totalPending === "number" ? { position, totalPending } : null;
}

export async function listSubmissionsByStatus(
  env: SubmissionApiEnv,
  status: string,
  limit: number,
): Promise<readonly SubmissionRow[]> {
  const order = status === "pending_verification"
    ? "coalesce(uploaded_at, created_at) asc, created_at asc, submission_id asc"
    : "coalesce(uploaded_at, validated_at, published_at, created_at) desc, created_at desc, submission_id asc";
  const rows = await env.DB.prepare(
    `${rowSelectSql("status")} order by ${order} limit ?`,
  )
    .bind(status, limit)
    .all();
  return rows.results.map((row) => SubmissionRowSchema.parse(row));
}

export async function listAcceptedFeed(env: SubmissionApiEnv, limit: number): Promise<readonly AcceptedFeedRow[]> {
  return listAcceptedFeedView(env, limit, "verified");
}

export async function listAcceptedFeedView(
  env: SubmissionApiEnv,
  limit: number,
  view: "provisional" | "verified",
): Promise<readonly AcceptedFeedRow[]> {
  let rows: { readonly results: readonly Record<string, unknown>[] };
  try {
    rows = await env.DB.prepare(
      `select submission_id, submitter_display_name, origin, suite_release_id, publish_state, validated_at, raw_bundle_sha256
       from submissions
       where status = 'accepted'
         and (${view === "provisional" ? "zt1_decision = 'provisional'" : "coalesce(zt1_decision, '') <> 'provisional'"})
       order by coalesce(validated_at, uploaded_at, published_at, created_at) desc, created_at desc
       limit ?`,
    )
      .bind(limit)
      .all();
  } catch (error) {
    if (zt1ColumnsMissing(error)) {
      if (view === "provisional") {
        return [];
      }
      rows = await env.DB.prepare(
        `select submission_id, submitter_display_name, origin, suite_release_id, publish_state, validated_at, raw_bundle_sha256
         from submissions
         where status = 'accepted'
         order by coalesce(validated_at, uploaded_at, published_at, created_at) desc, created_at desc
         limit ?`,
      )
        .bind(limit)
        .all();
    } else {
      throw error;
    }
  }
  return rows.results.map((row) => ({
    origin: text(row, "origin"),
    publish_state: text(row, "publish_state"),
    raw_bundle_sha256: text(row, "raw_bundle_sha256"),
    submission_id: text(row, "submission_id"),
    submitter_display_name: nullableText(row, "submitter_display_name"),
    suite_release_id: nullableText(row, "suite_release_id"),
    validated_at: nullableText(row, "validated_at"),
  }));
}

export async function publicTransitionHistory(
  env: SubmissionApiEnv,
  submissionId: string,
): Promise<readonly PublicTransitionHistory[]> {
  let rows: { readonly results: readonly Record<string, unknown>[] };
  try {
    rows = await env.DB.prepare(
      `select to_status, actor, reason, created_at
       from submission_transitions
       where submission_id = ?
       order by id asc`,
    )
      .bind(submissionId)
      .all();
  } catch (error) {
    if (transitionTableMissing(error)) {
      return [];
    }
    throw error;
  }
  return rows.results.map((row) => {
    const toStatus = text(row, "to_status");
    const history = {
      actor: text(row, "actor"),
      created_at: text(row, "created_at"),
      to_status: toStatus,
    };
    const reason = nullableText(row, "reason");
    return toStatus === "rejected" && reason !== null ? { ...history, reason } : history;
  });
}

export function publicSubmission(row: SubmissionRow): Record<string, string | number | null> {
  const result: Record<string, string | number | null> = {
    bundle_schema_version: row.bundle_schema_version,
    duplicate_of: row.duplicate_of,
    declared_model_slug: row.declared_model_slug,
    expires_at: row.status === "ticketed" ? row.expires_at : null,
    origin: row.origin,
    projection_sha256: row.projection_sha256,
    projection_object_sha256: row.projection_object_sha256,
    publish_state: row.publish_state,
    raw_bundle_size_bytes: row.raw_bundle_size_bytes,
    status: row.status,
    submission_id: row.submission_id,
    suite_release_id: row.suite_release_id,
    submitter_display_name: row.status === "accepted" ? row.submitter_display_name : null,
  };
  if (row.status === "rejected") {
    result["status_reason"] = row.status_reason;
  }
  return result;
}

function rowSelectSql(column: "submission_id" | "raw_bundle_sha256" | "status"): string {
  return `select submission_id, ticket_id, status, created_at, declared_model_slug, bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key,
    raw_bundle_size_bytes, projection_sha256, projection_object_sha256, publish_state, published_at, validated_at, suite_release_id, suite_manifest_sha256,
    origin, submitter_id, submitter_display_name, uploaded_at, expires_at, run_payload_sha256, duplicate_of, status_reason,
    upload_capability_sha256, state_revision
    from submissions where ${column} = ?`;
}

function parseRow(row: Record<string, unknown> | null): SubmissionRow | null {
  return row === null ? null : SubmissionRowSchema.parse(row);
}

export async function recordSubmissionTransition(env: SubmissionApiEnv, transition: TransitionRecord): Promise<void> {
  try {
    await env.DB.prepare(
      `insert into submission_transitions
        (submission_id, from_status, to_status, publish_state, actor, reason)
       values (?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        transition.submissionId,
        transition.fromStatus,
        transition.toStatus,
        transition.publishState,
        transition.actor,
        transition.reason ?? null,
      )
      .run();
  } catch (error) {
    if (transitionTableMissing(error)) {
      return;
    }
    throw error;
  }
}

async function requiredRow(env: SubmissionApiEnv, submissionId: string): Promise<SubmissionRow> {
  const row = await rowBySubmissionId(env, submissionId);
  if (row === null) {
    throw new InvalidTransitionError("unknown", "unknown");
  }
  return row;
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") {
    throw new Error(`${key} must be a string`);
  }
  return value;
}

function nullableText(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value === null || typeof value === "string") {
    return value;
  }
  throw new Error(`${key} must be a string or null`);
}

function transitionTableMissing(error: unknown): boolean {
  return error instanceof Error && error.message.includes("no such table: submission_transitions");
}

function zt1ColumnsMissing(error: unknown): boolean {
  return error instanceof Error && error.message.includes("zt1_decision");
}

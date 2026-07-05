import {
  ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
  RESULT_BUNDLE_SCHEMA_VERSION,
  SubmissionRowSchema,
  type ResultBundle,
  type StatusUpdate,
  type SubmissionApiEnv,
  type SubmissionEnvelope,
  type SubmissionRow,
} from "./submission-contracts";
import { InvalidTransitionError, assertTransition, type SubmissionStatus } from "./submission-state";
import { projectionKey, rawBundleKey } from "./submission-storage";

export type TransitionActor = "system" | "maintainer" | "gc";

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

export async function insertTicketedSubmission(env: SubmissionApiEnv, ticket: SubmissionEnvelope): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, submitter_display_name, ticket_id, status, bundle_schema_version,
      raw_bundle_sha256, raw_bundle_r2_key, suite_release_id, suite_manifest_sha256, expires_at, idempotency_key
    ) values (?, ?, ?, ?, ?, 'ticketed', ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      ticket.ticket_id,
      ticket.origin,
      ticket.submitter_id,
      ticket.submitter_display_name ?? null,
      ticket.ticket_id,
      RESULT_BUNDLE_SCHEMA_VERSION,
      ticket.bundle_sha256,
      rawBundleKey(ticket.bundle_sha256),
      ticket.expected_suite_release_id,
      ticket.expected_suite_manifest_sha256,
      ticket.expires_at,
      ticket.bundle_sha256,
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
  await env.DB.prepare(
    `update submissions set
      submission_id = ?, ticket_id = ?, submitter_id = ?, submitter_display_name = ?, origin = ?, suite_release_id = ?,
      suite_manifest_sha256 = ?, expires_at = ?, bundle_schema_version = ?
      where submission_id = ?`,
  )
    .bind(
      ticket.ticket_id,
      ticket.ticket_id,
      ticket.submitter_id,
      ticket.submitter_display_name ?? null,
      ticket.origin,
      ticket.expected_suite_release_id,
      ticket.expected_suite_manifest_sha256,
      ticket.expires_at,
      RESULT_BUNDLE_SCHEMA_VERSION,
      currentSubmissionId,
    )
    .run();
}

export async function markPendingVerification(
  env: SubmissionApiEnv,
  submissionId: string,
  bundle: ResultBundle,
  sizeBytes: number,
  runPayloadSha256: string,
  duplicateOf: string | null,
): Promise<void> {
  const current = await requiredRow(env, submissionId);
  assertTransition(current.status, "pending_verification");
  await env.DB.prepare(
    `update submissions set
      uploaded_at = datetime('now'), status = 'pending_verification', raw_bundle_size_bytes = ?,
      bundle_schema_version = ?, suite_release_id = ?, suite_manifest_sha256 = ?, tier = ?,
      run_payload_sha256 = ?, duplicate_of = ?
      where submission_id = ?`,
  )
    .bind(
      sizeBytes,
      RESULT_BUNDLE_SCHEMA_VERSION,
      bundle.manifest.suite.suite_release_id,
      bundle.manifest.suite.suite_manifest_sha256,
      bundle.tier,
      runPayloadSha256,
      duplicateOf,
      submissionId,
    )
    .run();
  await recordSubmissionTransition(env, {
    actor: "system",
    fromStatus: current.status,
    publishState: current.publish_state,
    reason: "upload completed",
    submissionId,
    toStatus: "pending_verification",
  });
}

export async function applyStatusUpdate(env: SubmissionApiEnv, submissionId: string, update: StatusUpdate): Promise<void> {
  const current = await requiredRow(env, submissionId);
  assertTransition(current.status, update.status);
  await env.DB.prepare(
    `update submissions set
      status = ?, status_reason = ?, validator_version = ?, validator_commit = ?, validated_at = ?,
      projection_schema_version = ?, projection_sha256 = ?, projection_r2_key = ?, redaction_status = 'public_projection_only'
      where submission_id = ?`,
  )
    .bind(
      update.status,
      update.reason,
      update.validator_version,
      update.validator_commit ?? null,
      update.validated_at,
      ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
      update.projection_sha256,
      projectionKey(submissionId, update.projection_sha256),
      submissionId,
    )
    .run();
  await recordSubmissionTransition(env, {
    actor: "maintainer",
    fromStatus: current.status,
    publishState: current.publish_state,
    reason: update.reason,
    submissionId,
    toStatus: update.status,
  });
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
  await env.DB.prepare(
    `update submissions set publish_state = ?, published_at = case when ? = 'published' then datetime('now') else published_at end where submission_id = ?`,
  )
    .bind(publishState, publishState, submissionId)
    .run();
  if (current.publish_state !== publishState) {
    await recordSubmissionTransition(env, {
      actor: "maintainer",
      fromStatus: current.status,
      publishState,
      reason,
      submissionId,
      toStatus: current.status,
    });
  }
}

export async function transitionAcceptedToTerminal(
  env: SubmissionApiEnv,
  submissionId: string,
  toStatus: "withdrawn" | "suppressed",
  reason: string,
): Promise<void> {
  const current = await requiredRow(env, submissionId);
  assertTransition(current.status, toStatus);
  await env.DB.prepare(
    "update submissions set status = ?, status_reason = ?, publish_state = 'hidden' where submission_id = ?",
  )
    .bind(toStatus, reason, submissionId)
    .run();
  await recordSubmissionTransition(env, {
    actor: "maintainer",
    fromStatus: current.status,
    publishState: "hidden",
    reason,
    submissionId,
    toStatus,
  });
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

export async function rowByPayloadSha(env: SubmissionApiEnv, runPayloadSha256: string): Promise<SubmissionRow | null> {
  return parseRow(
    await env.DB.prepare(rowSelectSql("run_payload_sha256"))
      .bind(runPayloadSha256)
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

export async function listSubmissionsByStatus(
  env: SubmissionApiEnv,
  status: string,
  limit: number,
): Promise<readonly SubmissionRow[]> {
  const rows = await env.DB.prepare(
    `${rowSelectSql("status")} order by coalesce(uploaded_at, validated_at, published_at, created_at) desc, created_at desc limit ?`,
  )
    .bind(status, limit)
    .all();
  return rows.results.map((row) => SubmissionRowSchema.parse(row));
}

export async function listAcceptedFeed(env: SubmissionApiEnv, limit: number): Promise<readonly AcceptedFeedRow[]> {
  const rows = await env.DB.prepare(
    `select submission_id, submitter_display_name, origin, suite_release_id, publish_state, validated_at, raw_bundle_sha256
     from submissions
     where status = 'accepted'
     order by coalesce(validated_at, uploaded_at, published_at, created_at) desc, created_at desc
     limit ?`,
  )
    .bind(limit)
    .all();
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
    expires_at: row.status === "ticketed" ? row.expires_at : null,
    origin: row.origin,
    projection_sha256: row.projection_sha256,
    publish_state: row.publish_state,
    raw_bundle_sha256: row.raw_bundle_sha256,
    raw_bundle_size_bytes: row.raw_bundle_size_bytes,
    status: row.status,
    submission_id: row.submission_id,
    suite_release_id: row.suite_release_id,
    submitter_display_name: row.submitter_display_name,
  };
  if (row.status === "rejected") {
    result["status_reason"] = row.status_reason;
  }
  return result;
}

function rowSelectSql(column: "submission_id" | "raw_bundle_sha256" | "run_payload_sha256" | "status"): string {
  return `select submission_id, ticket_id, status, bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key,
    raw_bundle_size_bytes, projection_sha256, publish_state, suite_release_id, suite_manifest_sha256,
    origin, submitter_id, submitter_display_name, uploaded_at, expires_at, run_payload_sha256, duplicate_of, status_reason
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

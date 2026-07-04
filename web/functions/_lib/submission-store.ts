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
import { projectionKey, rawBundleKey } from "./submission-storage";

export async function insertTicketedSubmission(env: SubmissionApiEnv, ticket: SubmissionEnvelope): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, ticket_id, status, bundle_schema_version,
      raw_bundle_sha256, raw_bundle_r2_key, suite_release_id, suite_manifest_sha256, expires_at, idempotency_key
    ) values (?, ?, ?, ?, 'ticketed', ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      ticket.ticket_id,
      ticket.origin,
      ticket.submitter_id,
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
}

export async function rotateTicketedSubmission(env: SubmissionApiEnv, currentSubmissionId: string, ticket: SubmissionEnvelope): Promise<void> {
  await env.DB.prepare(
    `update submissions set
      submission_id = ?, ticket_id = ?, submitter_id = ?, origin = ?, suite_release_id = ?,
      suite_manifest_sha256 = ?, expires_at = ?, bundle_schema_version = ?
      where submission_id = ?`,
  )
    .bind(
      ticket.ticket_id,
      ticket.ticket_id,
      ticket.submitter_id,
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
}

export async function applyStatusUpdate(env: SubmissionApiEnv, submissionId: string, update: StatusUpdate): Promise<void> {
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
}

export async function updatePublishState(env: SubmissionApiEnv, submissionId: string, publishState: "hidden" | "preview" | "published"): Promise<void> {
  await env.DB.prepare(
    `update submissions set publish_state = ?, published_at = case when ? = 'published' then datetime('now') else published_at end where submission_id = ?`,
  )
    .bind(publishState, publishState, submissionId)
    .run();
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

export function publicSubmission(row: SubmissionRow): Record<string, string | number | null> {
  const result: Record<string, string | number | null> = {
    bundle_schema_version: row.bundle_schema_version,
    duplicate_of: row.duplicate_of,
    expires_at: row.status === "ticketed" ? row.expires_at : null,
    projection_sha256: row.projection_sha256,
    publish_state: row.publish_state,
    raw_bundle_sha256: row.raw_bundle_sha256,
    raw_bundle_size_bytes: row.raw_bundle_size_bytes,
    status: row.status,
    submission_id: row.submission_id,
  };
  if (row.status === "rejected") {
    result["status_reason"] = row.status_reason;
  }
  return result;
}

function rowSelectSql(column: "submission_id" | "raw_bundle_sha256" | "run_payload_sha256" | "status"): string {
  return `select submission_id, ticket_id, status, bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key,
    raw_bundle_size_bytes, projection_sha256, publish_state, suite_release_id, suite_manifest_sha256,
    origin, submitter_id, uploaded_at, expires_at, run_payload_sha256, duplicate_of, status_reason
    from submissions where ${column} = ?`;
}

function parseRow(row: Record<string, unknown> | null): SubmissionRow | null {
  return row === null ? null : SubmissionRowSchema.parse(row);
}

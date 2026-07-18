import {
  ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
  type D1PreparedStatement,
  type StatusUpdate,
  type SubmissionApiEnv,
  type SubmissionRow,
} from "./submission-contracts";
import { InvalidTransitionError, assertTransition } from "./submission-state";
import { rowBySubmissionId, type TransitionActor } from "./submission-store";

export type VerificationMutation = {
  readonly actor: TransitionActor;
  readonly projectionR2Key: string | null;
  readonly submissionId: string;
  readonly update: StatusUpdate;
};

export async function applyInitialDecision(env: SubmissionApiEnv, mutation: VerificationMutation): Promise<void> {
  const current = await requiredRow(env, mutation.submissionId);
  assertTransition(current.status, mutation.update.status);
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for verification decisions");
  const accepted = mutation.update.status === "accepted";
  const reason = accepted ? mutation.update.reason : mutation.update.reason_code;
  const projectionSha = accepted ? mutation.update.projection_sha256 : null;
  const projectionObjectSha = accepted ? mutation.update.projection_object_sha256 : null;
  const statements: D1PreparedStatement[] = [
    env.DB.prepare(
      `update submissions set
        status = ?, status_reason = ?, validator_version = ?, validator_commit = ?, validated_at = ?,
        projection_schema_version = case when ? = 'accepted' then ? else projection_schema_version end,
        projection_sha256 = case when ? = 'accepted' then ? else projection_sha256 end,
        projection_object_sha256 = case when ? = 'accepted' then ? else projection_object_sha256 end,
        projection_r2_key = case when ? = 'accepted' then ? else projection_r2_key end,
        redaction_status = case when ? = 'accepted' then 'public_projection_only' else redaction_status end,
        state_revision = state_revision + 1
       where submission_id = ? and status = 'pending_verification' and state_revision = ?`,
    ).bind(
      mutation.update.status, reason, mutation.update.validator_version,
      mutation.update.validator_commit ?? null, mutation.update.validated_at,
      mutation.update.status, ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
      mutation.update.status, projectionSha, mutation.update.status, projectionObjectSha,
      mutation.update.status, mutation.projectionR2Key, mutation.update.status,
      mutation.submissionId, current.state_revision,
    ),
    env.DB.prepare(
      `insert into submission_transitions
        (submission_id, from_status, to_status, publish_state, actor, reason, state_revision)
       select ?, ?, ?, ?, ?, ?, ? where changes() = 1`,
    ).bind(
      mutation.submissionId, current.status, mutation.update.status, current.publish_state,
      mutation.actor, reason, current.state_revision + 1,
    ),
    env.DB.prepare(
      "update publication_control set publication_revision = publication_revision + 1, updated_at = datetime('now') where singleton = 1 and changes() = 1",
    ),
  ];
  appendAttestation(statements, env, current, mutation);
  const results = await env.DB.batch(statements);
  if (results[0]?.meta?.changes !== 1) throw new InvalidTransitionError(current.status, mutation.update.status);
}

export async function applyProjectionRefresh(env: SubmissionApiEnv, mutation: VerificationMutation): Promise<void> {
  const current = await requiredRow(env, mutation.submissionId);
  const update = mutation.update;
  if (update.status !== "accepted" || update.operation !== "projection_refresh") {
    throw new InvalidTransitionError(current.status, update.status);
  }
  const expectedRevision = update.expected_state_revision;
  const previousProjectionSha = update.previous_projection_object_sha256;
  if (expectedRevision === undefined || previousProjectionSha === undefined) {
    throw new InvalidTransitionError(current.status, "projection_refresh");
  }
  assertTransition(current.status, "accepted");
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for projection refresh");
  const statements: D1PreparedStatement[] = [
    env.DB.prepare(
      `update submissions set
        validator_version = ?, validator_commit = ?, validated_at = ?,
        projection_schema_version = ?, projection_sha256 = ?, projection_object_sha256 = ?,
        projection_r2_key = ?, redaction_status = 'public_projection_only', state_revision = state_revision + 1
       where submission_id = ? and status = 'accepted' and state_revision = ? and projection_object_sha256 = ?`,
    ).bind(
      update.validator_version, update.validator_commit ?? null, update.validated_at,
      ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION, update.projection_sha256,
      update.projection_object_sha256, mutation.projectionR2Key, mutation.submissionId,
      expectedRevision, previousProjectionSha,
    ),
    env.DB.prepare(
      `insert into submission_transitions
        (submission_id, from_status, to_status, publish_state, actor, reason, state_revision)
       select ?, 'accepted', 'accepted', ?, ?, 'reverified', ? where changes() = 1`,
    ).bind(mutation.submissionId, current.publish_state, mutation.actor, expectedRevision + 1),
    env.DB.prepare(
      "update publication_control set publication_revision = publication_revision + 1, updated_at = datetime('now') where singleton = 1 and changes() = 1",
    ),
  ];
  appendAttestation(statements, env, current, mutation);
  const results = await env.DB.batch(statements);
  if (results[0]?.meta?.changes !== 1) throw new InvalidTransitionError(current.status, "projection_refresh");
}

export async function refreshWasAlreadyApplied(
  env: SubmissionApiEnv,
  row: SubmissionRow,
  update: Extract<StatusUpdate, { readonly status: "accepted" }>,
): Promise<boolean> {
  if (update.operation !== "projection_refresh" || update.expected_state_revision === undefined) return false;
  if (row.projection_object_sha256 !== update.projection_object_sha256) return false;
  const transition = await env.DB.prepare(
    `select 1 as applied from submission_transitions
     where submission_id = ? and to_status = 'accepted' and reason = 'reverified' and state_revision = ?`,
  ).bind(row.submission_id, update.expected_state_revision + 1).first();
  return transition !== null;
}

function appendAttestation(
  statements: D1PreparedStatement[],
  env: SubmissionApiEnv,
  current: SubmissionRow,
  mutation: VerificationMutation,
): void {
  const update = mutation.update;
  if (update.status !== "accepted" || update.maintainer_attestation === undefined) return;
  statements.push(env.DB.prepare(
    `insert into maintainer_verification_attestations (
      submission_id, raw_bundle_sha256, projection_object_sha256, coding_receipt_sha256,
      suite_release_id, suite_manifest_sha256, maintainer_key_id, decision, revision
    ) select ?, ?, ?, ?, ?, ?, ?, ?, ? where changes() = 1`,
  ).bind(
    mutation.submissionId, update.raw_bundle_sha256, update.projection_object_sha256,
    update.maintainer_attestation.coding_receipt_sha256, current.suite_release_id,
    current.suite_manifest_sha256, update.maintainer_attestation.maintainer_key_id,
    update.maintainer_attestation.decision, current.state_revision + 1,
  ));
}

async function requiredRow(env: SubmissionApiEnv, submissionId: string): Promise<SubmissionRow> {
  const row = await rowBySubmissionId(env, submissionId);
  if (row === null) throw new InvalidTransitionError("unknown", "unknown");
  return row;
}

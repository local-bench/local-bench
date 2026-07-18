import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { canonicalJson } from "../functions/_lib/submission-canonical";
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
  MIGRATION_0012,
  MIGRATION_0013,
  MIGRATION_0014,
  MIGRATION_0015,
  RAW_BUNDLE_SHA,
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  TEST_COMMUNITY_GROUP_ID,
  createEnv,
  jsonRequest,
  sha256Hex,
  statusUpdate,
} from "./submission-test-support";

export const VALIDATOR_SECRET = "fixture-validator-secret";

export async function ptmEnv(autoPublish: boolean) {
  const base = await createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
      MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012, MIGRATION_0013, MIGRATION_0014,
      MIGRATION_0015,
    ],
  });
  const env = { ...base, VALIDATOR_API_SECRET: VALIDATOR_SECRET };
  await env.DB.prepare("update ops_settings set value = ? where key = 'auto_publish'")
    .bind(autoPublish ? "on" : "off").run();
  return env;
}

export type PtmEnv = Awaited<ReturnType<typeof ptmEnv>>;

export type PendingFixture = {
  readonly rawJson: string;
  readonly rawSha: string;
  readonly submissionId: string;
};

export async function insertPendingFixture(env: PtmEnv, fixture: PendingFixture): Promise<void> {
  await env.SUBMISSIONS.put(`submissions/raw/${fixture.rawSha}.json`, fixture.rawJson);
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, submitter_display_name, status, raw_bundle_sha256,
      raw_bundle_r2_key, raw_bundle_size_bytes, idempotency_key, publish_state, uploaded_at,
      suite_release_id, suite_manifest_sha256, community_model_group_id
    ) values (?, 'community', ?, 'Fixture Submitter', 'pending_verification', ?, ?, ?, ?, 'hidden', datetime('now'), ?, ?, ?)`,
  ).bind(
    fixture.submissionId, `public_key:${"e".repeat(64)}`, fixture.rawSha, `submissions/raw/${fixture.rawSha}.json`,
    fixture.rawJson.length, fixture.rawSha, SUITE_RELEASE_ID, SUITE_MANIFEST_SHA, TEST_COMMUNITY_GROUP_ID,
  ).run();
}

export type VerifyRequest = {
  readonly headers?: Record<string, string>;
  readonly submissionId: string;
  readonly update: unknown;
};

export function verifyUpdate(env: PtmEnv, input: VerifyRequest): Promise<Response> {
  return applyVerification({
    env,
    params: { submissionId: input.submissionId },
    request: jsonRequest(
      `/api/admin/submissions/${input.submissionId}/verification?override=true`,
      input.update,
      input.headers ?? { "x-localbench-admin-secret": ADMIN_SECRET },
    ),
  });
}

export function refreshedUpdate(
  expectedRevision: number,
  previousProjectionSha: string,
  validatedAt = "2026-07-19T00:00:00Z",
): Record<string, unknown> {
  const base = statusUpdate("accepted", RAW_BUNDLE_SHA, "community");
  const original = AcceptedResultProjectionV2Schema.parse(base["projection"]);
  const hashable = {
    ...original,
    artifact_hashes: {
      bundle_sha256: original.artifact_hashes.bundle_sha256,
      projection_sha256: "",
      public_artifact_manifest_sha256: "",
    },
    model: { ...original.model, display_name: "Refreshed Fixture Model" },
    validator: { ...original.validator, validated_at: validatedAt },
  };
  const projectionSha = sha256Hex(canonicalJson(hashable));
  const projection = {
    ...hashable,
    artifact_hashes: {
      bundle_sha256: original.artifact_hashes.bundle_sha256,
      projection_sha256: projectionSha,
      public_artifact_manifest_sha256: sha256Hex(canonicalJson({
        bundle_sha256: original.artifact_hashes.bundle_sha256,
        projection_sha256: projectionSha,
      })),
    },
  };
  return {
    ...base,
    expected_state_revision: expectedRevision,
    operation: "projection_refresh",
    previous_projection_object_sha256: previousProjectionSha,
    projection,
    projection_object_sha256: sha256Hex(canonicalJson(projection)),
    projection_sha256: projectionSha,
    validated_at: validatedAt,
  };
}

export async function storedBoard(env: PtmEnv): Promise<unknown> {
  const stored = await env.SUBMISSIONS.get("board/community-live.json");
  return stored === null ? null : new Response(stored.body).json();
}

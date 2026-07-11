import { readFileSync } from "node:fs";
import { expect } from "vitest";
import type { SubmissionApiEnv } from "../functions/_lib/submission-api";
import {
  ADMIN_SECRET,
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  PROJECTION_SHA,
  RAW_BUNDLE_SHA,
  applyMigration,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
} from "./submission-test-support";

export { RAW_BUNDLE_SHA };

const MIGRATION_0006 = readFileSync(new URL("../migrations/0006_zt0_foundation.sql", import.meta.url), "utf-8");

export async function createZt0Env(): Promise<SubmissionApiEnv> {
  const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
  for (const migration of [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011]) {
    await applyMigration(env.DB, migration);
  }
  return env;
}

export function adminJson(path: string, body: unknown): Request {
  return jsonRequest(path, body, { "x-localbench-admin-secret": ADMIN_SECRET });
}

export function adminGet(path: string): Request {
  return getRequest(path, { "x-localbench-admin-secret": ADMIN_SECRET });
}

export function adminEmptyPost(path: string): Request {
  return new Request(new URL(path, "https://localbench.test"), {
    headers: { "x-localbench-admin-secret": ADMIN_SECRET },
    method: "POST",
  });
}

export async function acceptedSubmission(
  env: SubmissionApiEnv,
  options: {
    readonly publishState: "hidden" | "preview" | "published";
    readonly rawSha?: string;
    readonly submitterDisplayName?: string;
    readonly validatedAt?: string;
  },
): Promise<string> {
  const ticket = await issueEnvelope(env, options.rawSha ?? RAW_BUNDLE_SHA, {
    submitter_display_name: options.submitterDisplayName,
  });
  await env.DB.prepare(
    `update submissions set
      status = 'accepted',
      publish_state = ?,
      projection_sha256 = ?,
      projection_r2_key = ?,
      validated_at = ?,
      uploaded_at = ?
     where submission_id = ?`,
  )
    .bind(
      options.publishState,
      PROJECTION_SHA,
      `projections/${ticket.ticket_id}/${PROJECTION_SHA}.json`,
      options.validatedAt ?? "2026-01-01T00:00:00Z",
      "2026-01-01T00:00:00Z",
      ticket.ticket_id,
    )
    .run();
  return ticket.ticket_id;
}

export type InsertSubmissionOptions = {
  readonly expiresAt?: string;
  readonly id: string;
  readonly projectionKey?: string;
  readonly rawKey?: string;
  readonly rawSha: string;
  readonly status: string;
  readonly statusReason?: string;
  readonly uploadedAt?: string;
  readonly validatedAt?: string;
};

export async function insertSubmission(env: SubmissionApiEnv, options: InsertSubmissionOptions): Promise<void> {
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, ticket_id, status, status_reason,
      bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key, raw_bundle_size_bytes,
      suite_release_id, suite_manifest_sha256, projection_sha256, projection_r2_key,
      publish_state, uploaded_at, expires_at, validated_at, idempotency_key
    ) values (?, 'community', 'public_key:test', ?, ?, ?, 'localbench.result_bundle.v1',
      ?, ?, 100, 'suite-v1-text-code-agentic-5axis-v1',
      '1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f',
      ?, ?, 'hidden', ?, ?, ?, ?)`,
  )
    .bind(
      options.id,
      options.id,
      options.status,
      options.statusReason ?? null,
      options.rawSha,
      options.rawKey ?? null,
      options.projectionKey === undefined ? null : PROJECTION_SHA,
      options.projectionKey ?? null,
      options.uploadedAt ?? null,
      options.expiresAt ?? null,
      options.validatedAt ?? null,
      options.rawSha,
    )
    .run();
}

export async function expectSubmissionRow(
  env: SubmissionApiEnv,
  submissionId: string,
  expected: Record<string, string | null>,
): Promise<void> {
  const row = await env.DB.prepare("select * from submissions where submission_id = ?").bind(submissionId).first();
  expect(row).toMatchObject(expected);
}

export async function expectTransition(
  env: SubmissionApiEnv,
  submissionId: string,
  expected: Record<string, string | null>,
): Promise<void> {
  const row = await env.DB.prepare(
    "select from_status, to_status, publish_state, actor, reason from submission_transitions where submission_id = ? order by id desc limit 1",
  )
    .bind(submissionId)
    .first();
  expect(row).toMatchObject(expected);
}

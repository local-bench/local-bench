import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach } from "vitest";
import { Miniflare } from "miniflare";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import type { SubmissionApiEnv } from "../functions/_lib/submission-api";

export const MIGRATION_0001 = readFileSync(new URL("../migrations/0001_online_submissions.sql", import.meta.url), "utf-8");
export const MIGRATION_0002 = readFileSync(new URL("../migrations/0002_submission_slice_index.sql", import.meta.url), "utf-8");
export const MIGRATION_0003 = readFileSync(new URL("../migrations/0003_submission_reconcile.sql", import.meta.url), "utf-8");
export const MIGRATION_0004 = readFileSync(new URL("../migrations/0004_submission_contract_v2.sql", import.meta.url), "utf-8");
export const MIGRATION_0005 = readFileSync(new URL("../migrations/0005_submitter_display_name.sql", import.meta.url), "utf-8");
export const MIGRATION_0006 = readFileSync(new URL("../migrations/0006_zt0_foundation.sql", import.meta.url), "utf-8");
export const MIGRATION_0007 = readFileSync(new URL("../migrations/0007_feedback.sql", import.meta.url), "utf-8");
export const ADMIN_SECRET = "test-admin-secret";
export const PROJECTION_SHA = "b".repeat(64);
export const SUITE_RELEASE_ID = "suite-v1-full-exec-6axis-v1";
export const SUITE_MANIFEST_SHA = "daf29f4da1da8701ae5c4168d6ecc31df6973cbfc4d92cb59c51fa35b3290b45";
export const RESULT_BUNDLE = resultBundle();
export const RESULT_BUNDLE_JSON = JSON.stringify(RESULT_BUNDLE);
export const RAW_BUNDLE_SHA = sha256Hex(RESULT_BUNDLE_JSON);

const miniflares: Miniflare[] = [];

afterEach(async () => {
  await Promise.all(miniflares.map((miniflare) => miniflare.dispose()));
  miniflares.length = 0;
});

export type TestEnvOptions = {
  readonly includeAdminSecret: boolean;
  readonly includeR2Secrets: boolean;
  readonly migrations?: readonly string[];
};

export type IssuedEnvelope = { readonly ticket_id: string };

export type MigrationError = {
  readonly message: string;
  readonly statement: string;
};

export type MigrationOptions = { readonly allowErrors?: boolean };

export async function createEnv(options: TestEnvOptions): Promise<SubmissionApiEnv> {
  const miniflare = new Miniflare({
    compatibilityDate: "2026-06-27",
    d1Databases: { DB: "localbench-test" },
    modules: true,
    r2Buckets: { SUBMISSIONS: "localbench-submissions" },
    script: "export default { fetch() { return new Response('ok'); } }",
  });
  miniflares.push(miniflare);
  const bindings = await miniflare.getBindings<SubmissionApiEnv>();
  for (const migration of options.migrations ?? [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006]) {
    await applyMigration(bindings.DB, migration);
  }
  return {
    ...bindings,
    LOCALBENCH_PUBLIC_BASE_URL: "https://local-bench.ai",
    ...(options.includeAdminSecret ? { ADMIN_API_SECRET: ADMIN_SECRET } : {}),
    ...(options.includeR2Secrets
      ? {
          R2_ACCESS_KEY_ID: "test-access-key",
          R2_ACCOUNT_ID: "test-account",
          R2_BUCKET_NAME: "localbench-submissions",
          R2_SECRET_ACCESS_KEY: "test-secret-key",
        }
      : {}),
  };
}

export async function issueEnvelope(
  env: SubmissionApiEnv,
  rawBundleSha = RAW_BUNDLE_SHA,
  overrides: Record<string, unknown> = {},
): Promise<IssuedEnvelope> {
  const response = await issueTicket({
    env,
    request: jsonRequest("/api/submissions/tickets", ticketRequest(rawBundleSha, overrides), {
      "x-localbench-admin-secret": ADMIN_SECRET,
    }),
  });
  if (response.status !== 201) {
    throw new Error(`ticket response status ${response.status}`);
  }
  const body = await response.json();
  if (!isIssuedEnvelope(body)) {
    throw new Error("ticket response did not include ticket_id");
  }
  return body;
}

export async function applyMigration(
  db: SubmissionApiEnv["DB"],
  sql: string,
  options: MigrationOptions = {},
): Promise<readonly MigrationError[]> {
  const errors: MigrationError[] = [];
  for (const statement of sqlStatements(sql)) {
    try {
      await db.prepare(statement).run();
    } catch (error) {
      if (options.allowErrors !== true) {
        throw error;
      }
      errors.push({ message: errorMessage(error), statement });
    }
  }
  return errors;
}

export async function columnCount(db: SubmissionApiEnv["DB"], tableName: string, columnName: string): Promise<number> {
  const row = await db.prepare("select count(*) as count from pragma_table_info(?) where name = ?")
    .bind(tableName, columnName)
    .first();
  return numericCount(row);
}

export async function indexExists(db: SubmissionApiEnv["DB"], indexName: string): Promise<boolean> {
  const row = await db.prepare("select count(*) as count from sqlite_master where type = 'index' and name = ?")
    .bind(indexName)
    .first();
  return numericCount(row) === 1;
}

export async function tableExists(db: SubmissionApiEnv["DB"], tableName: string): Promise<boolean> {
  const row = await db.prepare("select count(*) as count from sqlite_master where type = 'table' and name = ?")
    .bind(tableName)
    .first();
  return numericCount(row) === 1;
}

export function migrationContractV2WithoutTier(): string {
  const migration0002 = replaceOnce(MIGRATION_0002, "  tier text,\n", "");
  let migration0004 = replaceOnce(MIGRATION_0004, "  tier text,\n", "");
  migration0004 = replaceOnce(
    migration0004,
    "  suite_manifest_sha256, scorecard_id, model_identity_digest, model_display_name, lane_id, tier,\n",
    "  suite_manifest_sha256, scorecard_id, model_identity_digest, model_display_name, lane_id,\n",
  );
  migration0004 = replaceOnce(
    migration0004,
    "  model_identity_digest, model_display_name, lane_id, tier, validator_version, validator_commit,\n",
    "  model_identity_digest, model_display_name, lane_id, validator_version, validator_commit,\n",
  );
  return `${migration0002}\n${migration0004}\n${MIGRATION_0005}`;
}

export function ticketRequest(rawBundleSha = RAW_BUNDLE_SHA, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    accepted_suite_terms: true,
    bundle_sha256: rawBundleSha,
    declared_model_slug: "gemma-4-12b-q4",
    submitter_id: "project-anchor",
    ...overrides,
  };
}

export function getRequest(path: string, headers: Record<string, string> = {}): Request {
  return new Request(`https://local-bench.ai${path}`, {
    headers,
    method: "GET",
  });
}

export function jsonRequest(path: string, body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://local-bench.ai${path}`, {
    body: JSON.stringify(body),
    headers: { "content-type": "application/json", ...headers },
    method: "POST",
  });
}

export type ResultBundleOptions = { readonly suiteManifestSha?: string; readonly suiteReleaseId?: string };

export function resultBundle(options: ResultBundleOptions = {}): Record<string, unknown> {
  return {
    axis_status: {},
    benches: {},
    conformance: {},
    headline_complete: false,
    items: [],
    manifest: {
      integrity: { publishable: true },
      provenance: { localbench_repo_commit: "440f540" },
      suite: {
        coverage_profile_id: "full-exec-6axis-v1",
        suite_manifest_sha256: options.suiteManifestSha ?? SUITE_MANIFEST_SHA,
        suite_release_id: options.suiteReleaseId ?? SUITE_RELEASE_ID,
      },
    },
    model: {},
    producer: "localbench-cli",
    run_finished_at: "2026-06-30T00:00:01Z",
    run_started_at: "2026-06-30T00:00:00Z",
    schema_version: "localbench.result_bundle.v1",
    scores: {
      headline_score: null,
      known_headline_contribution: 0.6316,
      measured_headline_weight: 0.85,
      missing_headline_weight: 0.15,
      partial_composite: 0.7431,
      partial_composite_scope: "measured_headline_axes",
      rank_scope: "full-exec-6axis-v1",
    },
    serving_mode: "external_openai_compatible_endpoint",
    tier: "standard",
    totals: {},
    warnings: [],
  };
}

export function statusUpdate(status: "accepted" | "rejected"): Record<string, unknown> {
  return {
    accepted: status === "accepted",
    blocking_reasons: [],
    projection_path: "out/projection.json",
    projection_sha256: PROJECTION_SHA,
    raw_bundle_sha256: RAW_BUNDLE_SHA,
    reason: "publishable",
    schema_version: "localbench.submission_status_update.v1",
    status,
    validated_at: "2026-06-30T00:00:00Z",
    validator_commit: "440f540",
    validator_version: "localbench.submission-validator.v1",
  };
}

export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function sqlStatements(sql: string): readonly string[] {
  return sql
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("--"))
    .join("\n")
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function numericCount(row: Record<string, unknown> | null): number {
  const count = row?.["count"];
  if (typeof count !== "number") {
    throw new Error("count query did not return a numeric count");
  }
  return count;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function replaceOnce(value: string, search: string, replacement: string): string {
  const replaced = value.replace(search, replacement);
  if (replaced === value) {
    throw new Error(`test fixture replacement did not match: ${search.trim()}`);
  }
  return replaced;
}

function isIssuedEnvelope(value: unknown): value is IssuedEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "ticket_id" in value &&
    typeof value.ticket_id === "string"
  );
}

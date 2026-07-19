import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach } from "vitest";
import { Miniflare } from "miniflare";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import type { SubmissionApiEnv } from "../functions/_lib/submission-api";
import { canonicalJson } from "../functions/_lib/submission-canonical";

export const MIGRATION_0001 = readFileSync(new URL("../migrations/0001_online_submissions.sql", import.meta.url), "utf-8");
export const MIGRATION_0002 = readFileSync(new URL("../migrations/0002_submission_slice_index.sql", import.meta.url), "utf-8");
export const MIGRATION_0003 = readFileSync(new URL("../migrations/0003_submission_reconcile.sql", import.meta.url), "utf-8");
export const MIGRATION_0004 = readFileSync(new URL("../migrations/0004_submission_contract_v2.sql", import.meta.url), "utf-8");
export const MIGRATION_0005 = readFileSync(new URL("../migrations/0005_submitter_display_name.sql", import.meta.url), "utf-8");
export const MIGRATION_0006 = readFileSync(new URL("../migrations/0006_zt0_foundation.sql", import.meta.url), "utf-8");
export const MIGRATION_0007 = readFileSync(new URL("../migrations/0007_feedback.sql", import.meta.url), "utf-8");
export const MIGRATION_0008 = readFileSync(new URL("../migrations/0008_zt1_zero_touch.sql", import.meta.url), "utf-8");
export const MIGRATION_0009 = readFileSync(new URL("../migrations/0009_pending_verification_queue.sql", import.meta.url), "utf-8");
export const MIGRATION_0010 = readFileSync(new URL("../migrations/0010_submission_admission_security.sql", import.meta.url), "utf-8");
export const MIGRATION_0011 = readFileSync(new URL("../migrations/0011_publication_snapshots.sql", import.meta.url), "utf-8");
export const MIGRATION_0012 = readFileSync(new URL("../migrations/0012_maintainer_attestations.sql", import.meta.url), "utf-8");
export const MIGRATION_0013 = readFileSync(new URL("../migrations/0013_community_model_groups.sql", import.meta.url), "utf-8");
export const MIGRATION_0014 = readFileSync(new URL("../migrations/0014_projection_storage_fences.sql", import.meta.url), "utf-8");
export const MIGRATION_0015 = readFileSync(new URL("../migrations/0015_accounts.sql", import.meta.url), "utf-8");
export const MIGRATION_0016 = readFileSync(new URL("../migrations/0016_client_reported_projection.sql", import.meta.url), "utf-8");
export const ADMIN_SECRET = "test-admin-secret";
export const TEST_COMMUNITY_GROUP_ID = `community-group:${"1".repeat(32)}`;
export const SUITE_RELEASE_ID = "suite-v1-full-exec-6axis-v1";
export const SUITE_MANIFEST_SHA = "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468";
export const RESULT_BUNDLE = resultBundle({ semanticFull: true });
export const RESULT_BUNDLE_JSON = JSON.stringify(RESULT_BUNDLE);
export const RAW_BUNDLE_SHA = sha256Hex(RESULT_BUNDLE_JSON);
const PROJECTION_HASHABLE = {
  schema_version: "localbench.accepted_result_projection.v2",
  model: {
    display_name: "Community Model", declared_name: "Community Model", file_sha256: "a".repeat(64),
    identity_status: "maintainer_verified", model_system_key: `artifact:${"a".repeat(64)}`,
  },
  lineage: { base_model: [] }, runtime: { name: "llama.cpp", version: "b1" },
  suite_release_id: SUITE_RELEASE_ID, suite_manifest_sha256: SUITE_MANIFEST_SHA,
  scorecard_id: "local-intelligence-index-v3.0", coverage_profile_id: "full-exec-6axis-v1",
  headline_complete: false,
  scores: { headline_score: null, partial_composite: 0.5, partial_composite_scope: "measured_headline_axes", measured_headline_weight: 0.5, missing_headline_weight: 0.5, known_headline_contribution: 0.25, rank_scope: "full-exec-6axis-v1" },
  axes: { knowledge: { ci: null, n: 1, score: 0.5, status: "measured" } }, conformance: {},
  receipt_references: { coding_receipt_sha256: null },
  artifact_hashes: { bundle_sha256: RAW_BUNDLE_SHA, projection_sha256: "", public_artifact_manifest_sha256: "" },
  origin: "project_anchor", trust_label: "project_anchor", verification_level: "bundle_rescored",
  agentic_provenance: "none", rescore_modes: { mmlu_pro: "rescored" },
  validator: { validator_version: "localbench.submission-validator.v1", commit: "440f540", validated_at: "2026-06-30T00:00:00Z" },
} as const;
export const PROJECTION_SHA = sha256Hex(canonicalJson(PROJECTION_HASHABLE));
export const PROJECTION = {
  ...PROJECTION_HASHABLE,
  artifact_hashes: {
    bundle_sha256: RAW_BUNDLE_SHA,
    projection_sha256: PROJECTION_SHA,
    public_artifact_manifest_sha256: sha256Hex(canonicalJson({ bundle_sha256: RAW_BUNDLE_SHA, projection_sha256: PROJECTION_SHA })),
  },
} as const;
export const PROJECTION_OBJECT_SHA = sha256Hex(canonicalJson(PROJECTION));

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

export type IssuedEnvelope = { readonly ticket_id: string; readonly upload_capability: string };

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
  const migrations = options.migrations ?? [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014, MIGRATION_0015, MIGRATION_0016];
  for (const migration of migrations) {
    await applyMigration(bindings.DB, migration);
  }
  if (migrations.includes(MIGRATION_0013)) {
    await bindings.DB.prepare(
      "insert or ignore into community_model_groups (community_model_group_id, declared_model_name) values (?, 'Test community model')",
    ).bind(TEST_COMMUNITY_GROUP_ID).run();
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

export type ResultBundleOptions = { readonly semanticFull?: boolean; readonly suiteManifestSha?: string; readonly suiteReleaseId?: string };

export function resultBundle(options: ResultBundleOptions = {}): Record<string, unknown> {
  const fullBenchCounts = {
    amo: 39,
    appworld_c: 96,
    bigcodebench_hard: 148,
    ifbench: 294,
    mmlu_pro: 400,
    olymmath_hard: 100,
    tc_json_v1: 330,
  } as const;
  const benchCounts: Readonly<Record<string, number>> = options.semanticFull === true ? fullBenchCounts : {};
  const items = Object.entries(benchCounts).flatMap(([bench, count]) =>
    Array.from({ length: count }, (_, index) => ({ bench, id: `${bench}-${index + 1}` })),
  );
  return {
    axis_status: {
      axes: Object.fromEntries(
        (options.semanticFull === true ? ["agentic", "coding", "instruction_following", "knowledge", "math", "tool_calling"] : [])
          .map((axis) => [axis, { axis, reason: "ok", status: "measured" }]),
      ),
      schema_version: "localbench.axis-status.v1",
    },
    benches: Object.fromEntries(Object.entries(benchCounts).map(([bench, n]) => [bench, { n }])),
    conformance: {},
    headline_complete: options.semanticFull === true,
    manifest: {
      integrity: { blocking_reasons: [], missing_required_fields: [], publishable: true },
      ...(options.semanticFull === true ? { model: { file_sha256: "a".repeat(64) } } : {}),
      provenance: { localbench_repo_commit: "440f540" },
      suite: {
        coverage_profile_id: "full-exec-6axis-v1",
        suite_manifest_sha256: options.suiteManifestSha ?? SUITE_MANIFEST_SHA,
        suite_release_id: options.suiteReleaseId ?? SUITE_RELEASE_ID,
      },
    },
    model: options.semanticFull === true ? { file_sha256: "a".repeat(64) } : {},
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
    ...(options.semanticFull === true ? {
      suite_coverage: {
        expected_items: 1311,
        missing_items: [],
        observed_items: 1311,
        status: "complete",
      },
    } : {}),
    totals: options.semanticFull === true ? { n_items: items.length } : {},
    warnings: [],
    items,
  };
}

export function statusUpdate(
  status: "accepted" | "rejected",
  rawBundleSha = RAW_BUNDLE_SHA,
  origin: "community" | "project_anchor" = "project_anchor",
  codingReceiptSha256: string | null = null,
): Record<string, unknown> {
  const hashable = {
    ...PROJECTION_HASHABLE,
    model: {
      ...PROJECTION_HASHABLE.model,
      identity_status: origin === "community" ? "unverified" : "maintainer_verified",
    },
    origin,
    receipt_references: { coding_receipt_sha256: codingReceiptSha256 },
    trust_label: origin === "community" ? "community_self_submitted" : "project_anchor",
    artifact_hashes: { bundle_sha256: rawBundleSha, projection_sha256: "", public_artifact_manifest_sha256: "" },
  };
  const projectionSha = sha256Hex(canonicalJson(hashable));
  const projection = {
    ...hashable,
    artifact_hashes: {
      bundle_sha256: rawBundleSha,
      projection_sha256: projectionSha,
      public_artifact_manifest_sha256: sha256Hex(canonicalJson({ bundle_sha256: rawBundleSha, projection_sha256: projectionSha })),
    },
  };
  return {
    accepted: status === "accepted",
    blocking_reasons: [],
    operation: "initial_decision",
    projection_path: "out/projection.json",
    projection,
    projection_object_sha256: sha256Hex(canonicalJson(projection)),
    projection_sha256: projectionSha,
    raw_bundle_sha256: rawBundleSha,
    reason: "publishable",
    schema_version: "localbench.submission_status_update.v1",
    status,
    validated_at: "2026-06-30T00:00:00Z",
    validator_commit: "440f540",
    validator_version: "localbench.submission-validator.v1",
  };
}

export function completeProjection(
  rawBundleSha: string,
  origin: "community" | "project_anchor",
  score = 0.71,
): Record<string, unknown> {
  const axes = ["agentic", "coding", "instruction_following", "knowledge", "math", "tool_calling"] as const;
  const hashable = {
    schema_version: "localbench.accepted_result_projection.v2",
    model: {
      declared_name: "Complete Fixture Model",
      display_name: "Complete Fixture Model",
      file_sha256: "a".repeat(64),
      identity_status: origin === "community" ? "unverified" : "maintainer_verified",
      model_system_key: `artifact:${"a".repeat(64)}`,
    },
    lineage: { base_model: ["Base Model"] },
    runtime: { name: "llama.cpp", version: "b-reset" },
    suite_release_id: SUITE_RELEASE_ID,
    suite_manifest_sha256: SUITE_MANIFEST_SHA,
    scorecard_id: "local-intelligence-index-v4.1",
    coverage_profile_id: "full-exec-6axis-v1",
    index_version: "index-v4.1",
    headline_complete: true,
    scores: {
      headline_score: score,
      partial_composite: score,
      partial_composite_scope: "measured_headline_axes",
      measured_headline_weight: 1,
      missing_headline_weight: 0,
      known_headline_contribution: score,
      rank_scope: "full-exec-6axis-v1",
      composite_full: score,
    },
    axes: Object.fromEntries(axes.map((axis) => [axis, {
      ci: [Math.max(0, score - 0.02), Math.min(1, score + 0.02)],
      n: 10,
      score,
      status: "measured",
    }])),
    conformance: { status: "passed" },
    receipt_references: { coding_receipt_sha256: "b".repeat(64) },
    artifact_hashes: {
      bundle_sha256: rawBundleSha,
      projection_sha256: "",
      public_artifact_manifest_sha256: "",
    },
    origin,
    trust_label: origin === "community" ? "community_self_submitted" : "project_anchor",
    verification_level: "client_reported",
    agentic_provenance: origin === "community" ? "self_reported" : "project_attested",
    rescore_modes: {
      amo: "rescored",
      appworld_c: "verdict_carried",
      bigcodebench_hard: "verdict_carried",
      ifbench: "rescored",
      mmlu_pro: "rescored",
      olymmath_hard: "rescored",
      tc_json_v1: "rescored",
    },
    validator: {
      validator_version: "localbench-cli-0.4.3.dev0",
      commit: "reset-api-test",
      validated_at: "2026-07-19T00:00:00Z",
    },
  } as const;
  const projectionSha = sha256Hex(canonicalJson(hashable));
  return {
    ...hashable,
    artifact_hashes: {
      bundle_sha256: rawBundleSha,
      projection_sha256: projectionSha,
      public_artifact_manifest_sha256: sha256Hex(canonicalJson({
        bundle_sha256: rawBundleSha,
        projection_sha256: projectionSha,
      })),
    },
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

function isIssuedEnvelope(value: unknown): value is IssuedEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "ticket_id" in value &&
    typeof value.ticket_id === "string" &&
    "upload_capability" in value &&
    typeof value.upload_capability === "string"
  );
}

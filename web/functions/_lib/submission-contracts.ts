import { z } from "zod";

export type SqlValue = string | number | null;

export type D1PreparedStatement = {
  all(): Promise<{ readonly results: readonly Record<string, unknown>[] }> | { readonly results: readonly Record<string, unknown>[] };
  bind(...values: readonly SqlValue[]): D1PreparedStatement;
  first(): Promise<Record<string, unknown> | null> | Record<string, unknown> | null;
  run(): Promise<{ readonly success: boolean }> | { readonly success: boolean };
};

export type D1DatabaseBinding = {
  exec(sql: string): Promise<unknown>;
  prepare(query: string): D1PreparedStatement;
};

export type R2ObjectBodyBinding = {
  text(): Promise<string>;
};

export type R2BucketBinding = {
  get(key: string): Promise<R2ObjectBodyBinding | null>;
  put(key: string, value: string | ArrayBuffer | ArrayBufferView | Blob | ReadableStream): Promise<unknown>;
};

export type SubmissionApiEnv = {
  readonly ADMIN_API_SECRET?: string;
  readonly DB: D1DatabaseBinding;
  readonly LOCALBENCH_PUBLIC_BASE_URL?: string;
  readonly R2_ACCESS_KEY_ID?: string;
  readonly R2_ACCOUNT_ID?: string;
  readonly R2_BUCKET_NAME?: string;
  readonly R2_SECRET_ACCESS_KEY?: string;
  readonly SUBMISSIONS: R2BucketBinding;
};

export type RouteParams = {
  readonly submissionId?: string;
};

export type SubmissionEnvelope = {
  readonly accepted_suite_terms: true;
  readonly allowed_schema: typeof RESULT_BUNDLE_SCHEMA_VERSION;
  readonly bundle_sha256: string;
  readonly declared_model_slug?: string;
  readonly expected_suite_manifest_sha256: string | null;
  readonly expected_suite_release_id: string | null;
  readonly expiry: string;
  readonly max_upload_bytes: number;
  readonly one_use: true;
  readonly origin: "project_anchor";
  readonly schema_version: typeof SUBMISSION_ENVELOPE_SCHEMA_VERSION;
  readonly submitter_id: string;
  readonly ticket_id: string;
};

export const RESULT_BUNDLE_SCHEMA_VERSION = "localbench.result_bundle.v1";
export const SUBMISSION_ENVELOPE_SCHEMA_VERSION = "localbench.submission_envelope.v1";
export const STATUS_UPDATE_SCHEMA_VERSION = "localbench.submission_status_update.v1";
export const ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION = "localbench.accepted_result_projection.v1";
export const DEFAULT_MAX_UPLOAD_BYTES = 104_857_600;
export const DEFAULT_SUITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1";
export const DEFAULT_SUITE_MANIFEST_SHA256 = "b3fc40191c366d87b5537b12daa3d5c3680035238492c47996ab1f1b00d32231";
export const SUBMISSIONS_BUCKET_NAME = "localbench-submissions";

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const RemovedBundleFields = ["schema", "composite", "trust_tier", "serving_verification_level", "source", "output_path"] as const;

export const TicketRequestSchema = z
  .object({
    accepted_suite_terms: z.literal(true),
    bundle_sha256: Sha256Schema,
    declared_model_slug: z.string().min(1).max(200).optional(),
    expected_suite_manifest_sha256: Sha256Schema.nullable().optional(),
    expected_suite_release_id: z.string().min(1).nullable().optional(),
    max_upload_bytes: z.number().int().positive().max(DEFAULT_MAX_UPLOAD_BYTES).optional(),
    public_key: z.string().regex(/^[0-9a-f]{64}$/).optional(),
    submitter_id: z.string().min(1).optional(),
  })
  .refine((request) => request.submitter_id !== undefined || request.public_key !== undefined, {
    message: "submitter_id or public_key is required",
  });

export const UploadTargetRequestSchema = z.object({
  raw_bundle_sha256: Sha256Schema,
  ticket_id: z.string().min(1),
});

export const CompleteRequestSchema = z.object({
  raw_bundle_sha256: Sha256Schema,
  size_bytes: z.number().int().positive().max(DEFAULT_MAX_UPLOAD_BYTES).optional(),
});

export const StatusUpdateSchema = z
  .object({
    accepted: z.boolean(),
    blocking_reasons: z.array(z.string()),
    projection_path: z.string().min(1),
    projection_sha256: Sha256Schema,
    raw_bundle_sha256: Sha256Schema,
    reason: z.string().min(1),
    schema_version: z.literal(STATUS_UPDATE_SCHEMA_VERSION),
    status: z.enum(["accepted", "rejected"]),
    validated_at: z.string().min(1),
    validator_commit: z.string().nullable().optional(),
    validator_version: z.string().min(1),
  })
  .refine((update) => update.accepted === (update.status === "accepted"), {
    message: "accepted must match status",
  });

export const PublishStateDecisionSchema = z.object({
  publish_state: z.enum(["hidden", "preview", "published"]),
});

export const ResultBundleSchema = z
  .object({
    axis_status: z.record(z.string(), z.unknown()),
    benches: z.record(z.string(), z.unknown()),
    conformance: z.record(z.string(), z.unknown()),
    headline_complete: z.boolean(),
    items: z.array(z.unknown()),
    manifest: z
      .object({
        integrity: z.object({ publishable: z.boolean() }).passthrough(),
        provenance: z.record(z.string(), z.unknown()),
        suite: z
          .object({
            coverage_profile_id: z.string().min(1),
            suite_manifest_sha256: Sha256Schema,
            suite_release_id: z.string().min(1),
          })
          .passthrough(),
      })
      .passthrough(),
    model: z.record(z.string(), z.unknown()),
    producer: z.string().min(1),
    run_finished_at: z.string().min(1),
    run_started_at: z.string().min(1),
    schema_version: z.literal(RESULT_BUNDLE_SCHEMA_VERSION),
    scores: z.object({
      headline_score: z.number().nullable(),
      known_headline_contribution: z.number(),
      measured_headline_weight: z.number(),
      missing_headline_weight: z.number(),
      partial_composite: z.number(),
      partial_composite_scope: z.literal("measured_headline_axes"),
      rank_scope: z.string().min(1),
    }),
    serving_mode: z.string().min(1),
    tier: z.string().min(1),
    totals: z.record(z.string(), z.unknown()),
    warnings: z.array(z.unknown()),
  })
  .passthrough()
  .superRefine((bundle, context) => {
    for (const field of RemovedBundleFields) {
      if (field in bundle) {
        context.addIssue({ code: "custom", message: `removed result_bundle_v1 field: ${field}` });
      }
    }
    if ("canonical" in bundle.manifest.integrity) {
      context.addIssue({ code: "custom", message: "use manifest.integrity.publishable, not canonical" });
    }
  });

export const SubmissionRowSchema = z.object({
  bundle_schema_version: z.string().nullable(),
  projection_sha256: z.string().nullable(),
  publish_state: z.enum(["hidden", "preview", "published"]),
  raw_bundle_r2_key: z.string().nullable(),
  raw_bundle_sha256: Sha256Schema,
  raw_bundle_size_bytes: z.number().nullable(),
  status: z.string(),
  submission_id: z.string(),
  suite_manifest_sha256: Sha256Schema.nullable(),
  suite_release_id: z.string().nullable(),
  ticket_id: z.string().nullable(),
});

export type TicketRequest = z.infer<typeof TicketRequestSchema>;
export type ResultBundle = z.infer<typeof ResultBundleSchema>;
export type StatusUpdate = z.infer<typeof StatusUpdateSchema>;
export type SubmissionRow = z.infer<typeof SubmissionRowSchema>;

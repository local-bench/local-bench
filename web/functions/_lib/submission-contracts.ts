import { z } from "zod";

export type SqlValue = string | number | null;

export type D1PreparedStatement = {
  all(): Promise<{ readonly results: readonly Record<string, unknown>[] }> | { readonly results: readonly Record<string, unknown>[] };
  bind(...values: readonly SqlValue[]): D1PreparedStatement;
  first(): Promise<Record<string, unknown> | null> | Record<string, unknown> | null;
  run(): Promise<{ readonly success: boolean; readonly meta?: { readonly changes?: number } }> | { readonly success: boolean; readonly meta?: { readonly changes?: number } };
};

export type D1DatabaseBinding = {
  batch?(statements: readonly D1PreparedStatement[]): Promise<readonly { readonly success: boolean; readonly meta?: { readonly changes?: number } }[]>;
  exec(sql: string): Promise<unknown>;
  prepare(query: string): D1PreparedStatement;
};

export type R2ObjectBodyBinding = {
  readonly body: ReadableStream<Uint8Array>;
  readonly size?: number;
};

export type R2ObjectMetadataBinding = {
  readonly size?: number;
};

export type R2BucketBinding = {
  delete(key: string): Promise<unknown>;
  get(key: string): Promise<R2ObjectBodyBinding | null>;
  head?(key: string): Promise<R2ObjectMetadataBinding | null>;
  put(key: string, value: string | ArrayBuffer | ArrayBufferView | Blob | ReadableStream, options?: { readonly onlyIf?: { readonly etagDoesNotMatch?: string } }): Promise<unknown>;
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
  readonly TURNSTILE_ENABLED?: string;
  readonly ZT1_KNOWN_ARTIFACTS_JSON?: string;
  readonly ZT1_PROTECTED_KEYS_JSON?: string;
  readonly ZT1_PROTECTED_MODEL_PATTERNS_JSON?: string;
  readonly ZT1_TRUSTED_ATTESTER_PUBKEYS_JSON?: string;
};

export type RouteParams = {
  readonly submissionId?: string;
};

export type SubmissionEnvelope = {
  readonly accepted_suite_terms: true;
  readonly allowed_schema: typeof RESULT_BUNDLE_SCHEMA_VERSION;
  readonly bundle_sha256: string;
  readonly community_model_group_id?: string;
  readonly declared_model_slug?: string;
  readonly expected_suite_manifest_sha256: string | null;
  readonly expected_suite_release_id: string | null;
  readonly expires_at: string;
  readonly expiry: string;
  readonly max_upload_bytes: number;
  readonly one_use: true;
  readonly origin: "project_anchor" | "community";
  readonly schema_version: typeof SUBMISSION_ENVELOPE_SCHEMA_VERSION;
  readonly submitter_display_name?: string;
  readonly submitter_id: string;
  readonly ticket_id: string;
  readonly upload_capability: string;
};

export const RESULT_BUNDLE_SCHEMA_VERSION = "localbench.result_bundle.v1";
export const SUBMISSION_ENVELOPE_SCHEMA_VERSION = "localbench.submission_envelope.v2";
export const STATUS_UPDATE_SCHEMA_VERSION = "localbench.submission_status_update.v1";
export const ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION = "localbench.accepted_result_projection.v2";
export const ONE_SHOT_IDENTITY_SCHEMA_VERSION = "localbench.one_shot_identity.v1";
export const PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION = "localbench.publishability_preflight.v1";
// Admission streams bounded R2 chunks into DigestStream, so peak memory is O(chunk)
// in bundle size and is independent of this 64 MiB storage/abuse cap.
export const MAX_UPLOAD_BYTES = 67_108_864;
export const DEFAULT_MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES;
export const DEFAULT_SUITE_RELEASE_ID = "suite-v1-full-exec-6axis-v1";
export const DEFAULT_SUITE_MANIFEST_SHA256 = "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468";
export const SUBMISSIONS_BUCKET_NAME = "localbench-submissions";

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const HfRevisionSchema = z.string().regex(/^[0-9a-f]{40}$/);
const Ed25519PublicKeySchema = z.string().regex(/^[0-9a-f]{64}$/);
const Ed25519SignatureSchema = z.string().regex(/^[0-9a-f]{128}$/);
// Display-only submitter credit: 2-40 chars, alphanumeric at both ends, interior may
// add space . _ ' - (no slashes/colons, so it cannot smuggle a URL). Identity stays
// the Ed25519 key; admin acceptance is the moderation gate before anything publishes.
const SubmitterDisplayNameSchema = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,38}[A-Za-z0-9]$/);
const RemovedBundleFields = ["schema", "composite", "trust_tier", "serving_verification_level", "source", "output_path"] as const;
const PopSchema = z.object({
  signature: Ed25519SignatureSchema,
  timestamp: z.string().min(1),
});
const CatalogSlugSchema = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(120);
const UploadCapabilitySchema = z.string().regex(/^upload_[0-9a-f]{32}$/);
export const CommunityModelGroupIdSchema = z.string().regex(/^community-group:[0-9a-f]{32}$/);
const ScoreSchema = z.number().min(0).max(1);
const NullableScoreSchema = ScoreSchema.nullable();

const OneShotArtifactSchema = z.object({
  filename: z.string().min(1),
  quant_label: z.string().min(1),
  repo_id: z.string().min(1),
  revision: HfRevisionSchema,
  sha256: Sha256Schema,
  size_bytes: z.number().int().positive().nullable().optional(),
});

const OneShotIdentityEnvelopeSchema = z
  .object({
    artifact: OneShotArtifactSchema,
    catalog_model_id: z.string().min(1).nullable().optional(),
    cli_version: z.string().min(1),
    local_only: z.boolean(),
    publishable: z.boolean(),
    requested_model: z.string().min(1),
    schema_version: z.literal(ONE_SHOT_IDENTITY_SCHEMA_VERSION),
    source: z.literal("one_shot"),
    suite_manifest_sha256: Sha256Schema,
    suite_release_id: z.string().min(1),
  })
  .passthrough();

export const TicketRequestSchema = z.object({
  accepted_suite_terms: z.literal(true),
  bundle_sha256: Sha256Schema,
  community_model_group_id: CommunityModelGroupIdSchema.optional(),
  declared_model_slug: CatalogSlugSchema.optional(),
  expected_suite_manifest_sha256: Sha256Schema.nullable().optional(),
  expected_suite_release_id: z.string().min(1).nullable().optional(),
  max_upload_bytes: z.number().int().positive().max(MAX_UPLOAD_BYTES).optional(),
  pop: PopSchema.optional(),
  public_key: Ed25519PublicKeySchema.optional(),
  submitter_display_name: SubmitterDisplayNameSchema.optional(),
  submitter_id: z.string().min(1).optional(),
});

export const UploadTargetRequestSchema = z.object({
  raw_bundle_sha256: Sha256Schema,
  ticket_id: z.string().min(1),
  upload_capability: UploadCapabilitySchema,
});

export const CompleteRequestSchema = z.object({
  raw_bundle_sha256: Sha256Schema,
  // Advisory CLI field only; actual R2 metadata is the authority for the structured 413 path.
  size_bytes: z.number().int().positive().optional(),
});

const ProjectionAxisSchema = z.object({
  ci: z.tuple([ScoreSchema, ScoreSchema]).nullable(),
  n: z.number().int().min(0).max(10_000_000),
  score: NullableScoreSchema,
  status: z.enum(["measured", "not_measured", "invalid"]),
}).strict();
const RescoreModeSchema = z.enum(["rescored", "verdict_carried"]);
const AcceptedResultProjectionV2BaseSchema = z.object({
  schema_version: z.literal(ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION),
  model: z.object({
    display_name: z.string().nullable(), declared_name: z.string().nullable(), file_sha256: Sha256Schema.nullable(),
    file_size_bytes: z.number().int().positive().nullable().optional(), file_name: z.string().nullable().optional(),
    family: z.string().nullable().optional(), quant_label: z.string().nullable().optional(), format: z.string().nullable().optional(),
    tokenizer_digest: Sha256Schema.nullable().optional(), chat_template_digest: Sha256Schema.nullable().optional(),
    identity_status: z.enum(["unverified", "maintainer_verified"]),
    model_system_key: z.string().regex(/^(artifact|legacy-project-anchor):[0-9a-f]{64}$/),
  }).strict(),
  lineage: z.object({
    base_model: z.array(z.string().min(1)).refine(
      (items) => new Set(items).size === items.length,
      { message: "lineage.base_model must contain unique items" },
    ),
  }).strict(),
  runtime: z.object({
    name: z.string().min(1), version: z.string().min(1), kv_cache_quant: z.string().nullable().optional(),
    ctx_len_configured: z.number().int().positive().nullable().optional(), parallel_slots: z.number().int().positive().nullable().optional(),
    build_flags: z.string().nullable().optional(),
  }).strict(),
  suite_release_id: z.enum([
    "suite-v1-partial-text-code-4axis-v1", "suite-v1-text-code-agentic-5axis-v1", "suite-v1-full-exec-6axis-v1",
    "suite-v1-static-exec-5axis-v1", "suite-v1-static-core-diag-v1",
  ]),
  suite_manifest_sha256: Sha256Schema,
  scorecard_id: z.string().min(1), coverage_profile_id: z.string().min(1), headline_complete: z.boolean(),
  scores: z.object({
    headline_score: NullableScoreSchema, partial_composite: ScoreSchema,
    partial_composite_scope: z.literal("measured_headline_axes"), measured_headline_weight: ScoreSchema,
    missing_headline_weight: ScoreSchema, known_headline_contribution: ScoreSchema, rank_scope: z.string().min(1),
    composite_static: NullableScoreSchema.optional(), composite_full: NullableScoreSchema.optional(), static_index_version: z.string().min(1).optional(),
  }).strict(),
  axes: z.record(z.string(), ProjectionAxisSchema).refine((axes) => Object.keys(axes).length > 0),
  conformance: z.object({
    status: z.string().min(1).optional(), n_scored: z.number().int().nonnegative().optional(),
    worst_bench: z.string().nullable().optional(), reasons: z.array(z.string()).optional(),
    per_bench: z.record(z.string(), z.unknown()).optional(),
  }).strict(),
  receipt_references: z.object({ coding_receipt_sha256: Sha256Schema.nullable() }).strict(),
  artifact_hashes: z.object({ bundle_sha256: Sha256Schema, projection_sha256: Sha256Schema, public_artifact_manifest_sha256: Sha256Schema }).strict(),
  origin: z.enum(["project_anchor", "community"]),
  trust_label: z.enum(["project_anchor", "community_self_submitted", "community_re_scored"]),
  verification_level: z.literal("bundle_rescored"), agentic_provenance: z.enum(["none", "project_attested", "self_reported"]),
  provenance_notes: z.array(z.string()).optional(),
  rescore_modes: z.object({
    amo: RescoreModeSchema.optional(), appworld_c: RescoreModeSchema.optional(), bfcl: RescoreModeSchema.optional(),
    bigcodebench_hard: RescoreModeSchema.optional(), ifbench: RescoreModeSchema.optional(), lcb: RescoreModeSchema.optional(),
    mmlu_pro: RescoreModeSchema.optional(),
    olymmath_hard: RescoreModeSchema.optional(), tc_json_v1: RescoreModeSchema.optional(),
  }).strict(),
  validator: z.object({ validator_version: z.string().min(1), commit: z.string().nullable(), validated_at: z.iso.datetime() }).strict(),
}).strict();

const SUITE_MANIFESTS: Readonly<Record<string, string>> = {
  "suite-v1-full-exec-6axis-v1": "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
  "suite-v1-static-exec-5axis-v1": "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
  "suite-v1-partial-text-code-4axis-v1": "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7",
  "suite-v1-text-code-agentic-5axis-v1": "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f",
  "suite-v1-static-core-diag-v1": "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69",
};

export const AcceptedResultProjectionV2Schema = AcceptedResultProjectionV2BaseSchema.superRefine((projection, context) => {
  if (SUITE_MANIFESTS[projection.suite_release_id] !== projection.suite_manifest_sha256) {
    context.addIssue({ code: "custom", message: "suite release manifest mismatch" });
  }
  if (projection.origin === "community" && (
    projection.model.identity_status !== "unverified" || projection.model.file_sha256 === null ||
    !projection.model.model_system_key.startsWith("artifact:")
  )) {
    context.addIssue({ code: "custom", message: "community projection identity is invalid" });
  }
});

export const StatusUpdateSchema = z
  .object({
    accepted: z.boolean(),
    blocking_reasons: z.array(z.string()),
    projection_path: z.string().min(1),
    projection: AcceptedResultProjectionV2Schema,
    projection_object_sha256: Sha256Schema,
    projection_sha256: Sha256Schema,
    raw_bundle_sha256: Sha256Schema,
    reason: z.string().min(1),
    schema_version: z.literal(STATUS_UPDATE_SCHEMA_VERSION),
    status: z.enum(["accepted", "rejected"]),
    validated_at: z.string().min(1),
    validator_commit: z.string().nullable().optional(),
    validator_version: z.string().min(1),
    maintainer_attestation: z.object({
      coding_receipt_sha256: Sha256Schema,
      decision: z.enum(["verified", "not_verified"]),
      maintainer_key_id: z.string().min(1).max(120),
    }).optional(),
  })
  .refine((update) => update.accepted === (update.status === "accepted"), {
    message: "accepted must match status",
  });

export const PublishStateDecisionSchema = z.object({
  publish_state: z.enum(["hidden", "preview", "published"]),
});

export const ModerationReasonSchema = z.object({
  reason: z.string().min(1).max(500),
});

export const OpsSettingsUpdateSchema = z.object({
  actor: z.enum(["owner", "agent", "security"]),
  key: z.literal("auto_publish"),
  value: z.enum(["on", "off"]),
});

export const GcRequestSchema = z.object({
  apply: z.boolean().default(false),
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

export const PublishabilityPreflightRequestSchema = z
  .object({
    artifact: OneShotArtifactSchema,
    catalog_model_id: z.string().min(1).nullable().optional(),
    cli_version: z.string().min(1),
    identity_envelope: OneShotIdentityEnvelopeSchema,
    quant_label: z.string().min(1),
    result_bundle: ResultBundleSchema.optional(),
    schema_version: z.literal(PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION),
    source: z.literal("one_shot"),
    suite_manifest_sha256: Sha256Schema,
    suite_release_id: z.string().min(1),
  })
  .passthrough()
  .superRefine((preflight, context) => {
    if (preflight.identity_envelope.suite_release_id !== preflight.suite_release_id) {
      context.addIssue({ code: "custom", message: "identity envelope suite_release_id mismatch" });
    }
    if (preflight.identity_envelope.suite_manifest_sha256 !== preflight.suite_manifest_sha256) {
      context.addIssue({ code: "custom", message: "identity envelope suite_manifest_sha256 mismatch" });
    }
    if (preflight.identity_envelope.artifact.revision !== preflight.artifact.revision) {
      context.addIssue({ code: "custom", message: "identity envelope artifact revision mismatch" });
    }
    if (preflight.identity_envelope.artifact.sha256 !== preflight.artifact.sha256) {
      context.addIssue({ code: "custom", message: "identity envelope artifact sha256 mismatch" });
    }
    if (preflight.result_bundle !== undefined) {
      const suite = preflight.result_bundle.manifest.suite;
      if (suite.suite_release_id !== preflight.suite_release_id) {
        context.addIssue({ code: "custom", message: "result bundle suite_release_id mismatch" });
      }
      if (suite.suite_manifest_sha256 !== preflight.suite_manifest_sha256) {
        context.addIssue({ code: "custom", message: "result bundle suite_manifest_sha256 mismatch" });
      }
    }
  });

export const SubmissionRowSchema = z.object({
  bundle_schema_version: z.string().nullable(),
  created_at: z.string(),
  declared_model_slug: z.string().nullable().optional().default(null),
  duplicate_of: z.string().nullable(),
  expires_at: z.string().nullable(),
  origin: z.enum(["project_anchor", "community"]),
  projection_sha256: z.string().nullable(),
  projection_object_sha256: z.string().nullable().optional().default(null),
  publish_state: z.enum(["hidden", "preview", "published"]),
  raw_bundle_r2_key: z.string().nullable(),
  raw_bundle_sha256: Sha256Schema,
  raw_bundle_size_bytes: z.number().nullable(),
  run_payload_sha256: Sha256Schema.nullable(),
  status: z.string(),
  status_reason: z.string().nullable(),
  state_revision: z.number().int().nonnegative().optional().default(0),
  submission_id: z.string(),
  submitter_display_name: z.string().nullable(),
  submitter_id: z.string().nullable(),
  suite_manifest_sha256: Sha256Schema.nullable(),
  suite_release_id: z.string().nullable(),
  ticket_id: z.string().nullable(),
  uploaded_at: z.string().nullable(),
  upload_capability_sha256: Sha256Schema.nullable().optional().default(null),
});

export type TicketRequest = z.infer<typeof TicketRequestSchema>;
export type PublishabilityPreflightRequest = z.infer<typeof PublishabilityPreflightRequestSchema>;
export type ResultBundle = z.infer<typeof ResultBundleSchema>;
export type StatusUpdate = z.infer<typeof StatusUpdateSchema>;
export type SubmissionRow = z.infer<typeof SubmissionRowSchema>;

import { z } from "zod";

export const ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION = "localbench.accepted_result_projection.v2";

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const HfRevisionSchema = z.string().regex(/^[0-9a-f]{40}$/);
const ScoreSchema = z.number().min(0).max(1);
const NullableScoreSchema = ScoreSchema.nullable();
const NullableNonnegativeNumberSchema = z.number().finite().nonnegative().nullable();
const UnsafeTextPattern = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const UnsafeMultilineTextPattern = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const UnsafeProjectionValuePattern = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;

function boundedSafeString(maxLength: number, minLength = 0): z.ZodString {
  return z.string().min(minLength).max(maxLength).refine((value) => !UnsafeTextPattern.test(value), {
    message: "text contains prohibited control or bidi characters",
  });
}

function boundedMultilineSafeString(maxLength: number, minLength = 0): z.ZodString {
  return z.string().min(minLength).max(maxLength).refine((value) => !UnsafeMultilineTextPattern.test(value), {
    message: "text contains prohibited control or bidi characters",
  });
}

const HfRepoSchema = boundedSafeString(140, 3).regex(/^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/);
const HfFilenameSchema = boundedSafeString(240, 1).refine(
  (value) => !value.startsWith("/") && !value.includes("\\") && !value.includes("://") && !value.split("/").includes(".."),
  { message: "HF filename must be a safe repository-relative path" },
);
const ProjectionAxisSchema = z.object({
  ci: z.tuple([ScoreSchema, ScoreSchema]).nullable(),
  n: z.number().int().min(0).max(10_000_000),
  score: NullableScoreSchema,
  status: z.enum(["measured", "not_measured", "invalid"]),
}).strict().superRefine((axis, context) => {
  if (axis.ci !== null && (axis.score === null || axis.ci[0] > axis.score || axis.score > axis.ci[1])) {
    context.addIssue({ code: "custom", message: "axis confidence interval must contain its score" });
  }
  if (axis.status === "measured" && (axis.score === null || axis.n === 0)) {
    context.addIssue({ code: "custom", message: "measured axis requires a score and samples" });
  }
  if (axis.status === "not_measured" && axis.score !== null) {
    context.addIssue({ code: "custom", message: "not-measured axis cannot carry a score" });
  }
});
// Headline axes are weighted by the index; suites also emit diagnostic axes
// (e.g. long_context, not_measured) that the CLI includes and the composite ignores.
// Bound the record for safety but do not allowlist names to the five headline axes,
// or every real submission carrying a diagnostic axis would be rejected.
const ProjectionAxesSchema = z.record(boundedSafeString(40, 1), ProjectionAxisSchema)
  .refine((axes) => Object.keys(axes).length > 0 && Object.keys(axes).length <= 16, {
    message: "projection must carry between 1 and 16 axes",
  });
const RescoreModeSchema = z.enum(["rescored", "verdict_carried"]);

export const ACCEPTED_PROJECTION_SUITE_RELEASE_IDS = [
  "suite-v1-partial-text-code-4axis-v1",
  "suite-v1-text-code-agentic-5axis-v1",
  "suite-v1-full-exec-6axis-v1",
  "suite-v1-static-exec-5axis-v1",
  "suite-v1-static-core-diag-v1",
  "suite-v2-full-exec-tooluse-5axis-v2",
] as const;
export const ACCEPTED_PROJECTION_INDEX_VERSIONS = ["index-v3.0", "index-v4.0", "index-v4.1", "index-v4.2"] as const;
export const ACCEPTED_PROJECTION_RESCORE_MODE_KEYS = [
  "amo",
  "appworld_c",
  "bfcl",
  "bfcl_multi_turn_base",
  "bfcl_multi_turn_long_context",
  "bigcodebench_hard",
  "ifbench",
  "lcb",
  "mmlu_pro",
  "olymmath_hard",
  "tc_json_v1",
] as const;
const AcceptedProjectionRescoreModesShape = Object.fromEntries(
  ACCEPTED_PROJECTION_RESCORE_MODE_KEYS.map((key) => [key, RescoreModeSchema.optional()]),
);
const CompositeFieldSchema = z.enum(["headline_score", "partial_composite", "composite_full"]);
const NormalizationAnnotationSchema = z.object({
  client_values: z.object({
    composite_full: NullableScoreSchema,
    headline_score: NullableScoreSchema,
    partial_composite: ScoreSchema,
  }).strict(),
  code: z.literal("client_composite_drift"),
  fields: z.array(CompositeFieldSchema).min(1).max(3).refine((fields) => new Set(fields).size === fields.length),
  server_value: ScoreSchema,
}).strict();
const ConformanceScalarSchema = z.union([
  z.boolean(),
  z.number(),
  boundedMultilineSafeString(300),
  z.null(),
]);

function boundedConformanceValue(depth: number): z.ZodType<unknown> {
  if (depth === 0) return ConformanceScalarSchema;
  const child = boundedConformanceValue(depth - 1);
  return z.union([
    ConformanceScalarSchema,
    z.array(child).max(64),
    z.record(boundedSafeString(120, 1), child).refine((value) => Object.keys(value).length <= 64),
  ]);
}

const ConformancePerBenchSchema = z.record(
  boundedSafeString(120, 1),
  boundedConformanceValue(4),
).refine((value) => Object.keys(value).length <= 64);

const RunEnvironmentRuntimeSchema = z.object({
  backend: boundedSafeString(120).nullable(),
  name: boundedSafeString(120).nullable(),
  version: boundedSafeString(120).nullable(),
}).strict();

const LegacyRuntimeSchema = z.object({
  name: boundedSafeString(120, 1), version: boundedSafeString(120, 1),
  kv_cache_quant: boundedSafeString(64, 1).nullable().optional(),
  ctx_len_configured: z.number().int().positive().nullable().optional(),
  parallel_slots: z.number().int().positive().nullable().optional(),
  build_flags: boundedMultilineSafeString(500).nullable().optional(),
}).strict();

const AcceptedResultProjectionV2BaseSchema = z.object({
  schema_version: z.literal(ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION),
  model: z.object({
    display_name: boundedSafeString(120).nullable(), declared_name: boundedSafeString(120).nullable(), file_sha256: Sha256Schema.nullable(),
    file_size_bytes: z.number().int().positive().nullable().optional(), file_name: boundedSafeString(140).nullable().optional(),
    family: boundedSafeString(64).nullable().optional(), quant_label: boundedSafeString(32).nullable().optional(), format: boundedSafeString(64).nullable().optional(),
    hf: z.object({ filename: HfFilenameSchema, repo: HfRepoSchema, revision: HfRevisionSchema }).strict().optional(),
    tokenizer_digest: Sha256Schema.nullable().optional(), chat_template_digest: Sha256Schema.nullable().optional(),
    identity_status: z.enum(["unverified", "maintainer_verified"]),
    model_system_key: z.string().regex(/^(artifact|legacy-project-anchor):[0-9a-f]{64}$/),
  }).strict(),
  lineage: z.object({
    base_model: z.array(boundedSafeString(140, 1)).max(8).refine(
      (items) => new Set(items).size === items.length,
      { message: "lineage.base_model must contain unique items" },
    ),
  }).strict(),
  runtime: z.union([RunEnvironmentRuntimeSchema, LegacyRuntimeSchema]).optional(),
  hardware: z.object({
    gpu_name: boundedSafeString(160).nullable(),
    vram_gb: NullableNonnegativeNumberSchema,
  }).strict().optional(),
  perf: z.object({
    decode_tps: NullableNonnegativeNumberSchema,
    wall_time_seconds: NullableNonnegativeNumberSchema,
    tokens_to_answer_median: NullableNonnegativeNumberSchema,
  }).strict().optional(),
  suite_release_id: z.enum(ACCEPTED_PROJECTION_SUITE_RELEASE_IDS),
  suite_manifest_sha256: Sha256Schema,
  scorecard_id: boundedSafeString(120, 1), coverage_profile_id: boundedSafeString(120, 1),
  index_version: z.enum(ACCEPTED_PROJECTION_INDEX_VERSIONS).optional(), headline_complete: z.boolean(),
  scores: z.object({
    headline_score: NullableScoreSchema, partial_composite: ScoreSchema,
    partial_composite_scope: z.literal("measured_headline_axes"), measured_headline_weight: ScoreSchema,
    missing_headline_weight: ScoreSchema, known_headline_contribution: ScoreSchema, rank_scope: boundedSafeString(120, 1),
    composite_static: NullableScoreSchema.optional(), composite_full: NullableScoreSchema.optional(), static_index_version: boundedSafeString(120, 1).optional(),
  }).strict(),
  axes: ProjectionAxesSchema,
  conformance: z.object({
    status: boundedSafeString(80, 1).optional(), n_scored: z.number().int().nonnegative().optional(),
    worst_bench: boundedSafeString(120, 1).nullable().optional(), reasons: z.array(boundedSafeString(300)).max(32).optional(),
    per_bench: ConformancePerBenchSchema.optional(),
  }).strict(),
  receipt_references: z.object({ coding_receipt_sha256: Sha256Schema.nullable() }).strict(),
  artifact_hashes: z.object({ bundle_sha256: Sha256Schema, projection_sha256: Sha256Schema, public_artifact_manifest_sha256: Sha256Schema }).strict(),
  origin: z.enum(["project_anchor", "community"]),
  trust_label: z.enum(["project_anchor", "community_self_submitted", "community_re_scored"]),
  verification_level: z.enum(["bundle_rescored", "spot_reproduced", "client_reported"]),
  agentic_provenance: z.enum(["none", "project_attested", "self_reported"]),
  normalization_annotations: z.array(NormalizationAnnotationSchema).max(1).optional(),
  provenance_notes: z.array(boundedSafeString(300)).max(128).optional(),
  rescore_modes: z.object(AcceptedProjectionRescoreModesShape).strict(),
  validator: z.object({
    validator_version: boundedSafeString(120, 1),
    commit: boundedSafeString(120, 1).nullable(),
    validated_at: z.iso.datetime(),
  }).strict(),
}).strict();

const SUITE_MANIFESTS: Readonly<Record<string, string>> = {
  "suite-v1-full-exec-6axis-v1": "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
  "suite-v1-static-exec-5axis-v1": "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
  "suite-v1-partial-text-code-4axis-v1": "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7",
  "suite-v1-text-code-agentic-5axis-v1": "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f",
  "suite-v1-static-core-diag-v1": "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69",
  "suite-v2-full-exec-tooluse-5axis-v2": "81420326194941f2dc2ec9146e5fc0dc06a8dca574b582a46ee6e0a1f7d1c734",
};

export const AcceptedResultProjectionV2Schema = AcceptedResultProjectionV2BaseSchema.superRefine((projection, context) => {
  if (containsUnsafeText(projection)) {
    context.addIssue({ code: "custom", message: "projection contains prohibited control or bidi characters" });
  }
  const expectedManifest = SUITE_MANIFESTS[projection.suite_release_id];
  if (expectedManifest !== undefined && expectedManifest !== projection.suite_manifest_sha256) {
    context.addIssue({ code: "custom", message: "suite release manifest mismatch" });
  }
  if (projection.origin === "community" && (
    projection.model.identity_status !== "unverified" || projection.model.file_sha256 === null ||
    !projection.model.model_system_key.startsWith("artifact:")
  )) {
    context.addIssue({ code: "custom", message: "community projection identity is invalid" });
  }
});

function containsUnsafeText(value: unknown): boolean {
  if (typeof value === "string") return UnsafeProjectionValuePattern.test(value);
  if (Array.isArray(value)) return value.some(containsUnsafeText);
  if (typeof value !== "object" || value === null) return false;
  return Object.entries(value).some(([key, entry]) => UnsafeTextPattern.test(key) || containsUnsafeText(entry));
}

export type AcceptedResultProjectionV2 = z.infer<typeof AcceptedResultProjectionV2Schema>;

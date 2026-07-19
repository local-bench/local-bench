import { z } from "zod";

export const RESULT_BUNDLE_SCHEMA_VERSION = "localbench.result_bundle.v1";
export const ONE_SHOT_IDENTITY_SCHEMA_VERSION = "localbench.one_shot_identity.v1";
export const PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION = "localbench.publishability_preflight.v1";

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const HfRevisionSchema = z.string().regex(/^[0-9a-f]{40}$/);
const RemovedBundleFields = [
  "schema",
  "composite",
  "trust_tier",
  "serving_verification_level",
  "source",
  "output_path",
] as const;

const OneShotArtifactSchema = z.object({
  filename: z.string().min(1),
  quant_label: z.string().min(1),
  repo_id: z.string().min(1),
  revision: HfRevisionSchema,
  sha256: Sha256Schema,
  size_bytes: z.number().int().positive().nullable().optional(),
});

const OneShotIdentityEnvelopeSchema = z.object({
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
}).passthrough();

export const ResultBundleSchema = z.object({
  axis_status: z.record(z.string(), z.unknown()),
  benches: z.record(z.string(), z.unknown()),
  conformance: z.record(z.string(), z.unknown()),
  headline_complete: z.boolean(),
  items: z.array(z.unknown()),
  manifest: z.object({
    integrity: z.object({ publishable: z.boolean() }).passthrough(),
    provenance: z.record(z.string(), z.unknown()),
    suite: z.object({
      coverage_profile_id: z.string().min(1),
      suite_manifest_sha256: Sha256Schema,
      suite_release_id: z.string().min(1),
    }).passthrough(),
  }).passthrough(),
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
}).passthrough().superRefine((bundle, context) => {
  for (const field of RemovedBundleFields) {
    if (field in bundle) {
      context.addIssue({ code: "custom", message: `removed result_bundle_v1 field: ${field}` });
    }
  }
  if ("canonical" in bundle.manifest.integrity) {
    context.addIssue({ code: "custom", message: "use manifest.integrity.publishable, not canonical" });
  }
});

export const PublishabilityPreflightRequestSchema = z.object({
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
}).passthrough().superRefine((preflight, context) => {
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

export type PublishabilityPreflightRequest = z.infer<typeof PublishabilityPreflightRequestSchema>;
export type ResultBundle = z.infer<typeof ResultBundleSchema>;

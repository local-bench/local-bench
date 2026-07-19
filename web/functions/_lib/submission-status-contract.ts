import { z } from "zod";
import { AcceptedResultProjectionV2Schema } from "./accepted-result-projection-contract";

export const STATUS_UPDATE_SCHEMA_VERSION = "localbench.submission_status_update.v1";
export const REJECTION_REASON_CODES = [
  "bundle_unreadable",
  "manifest_invalid",
  "schema_violation",
  "suite_mismatch",
  "identity_mismatch",
  "rescore_failed",
  "item_count_mismatch",
  "sampler_violation",
  "signature_invalid",
  "size_violation",
  "internal_error",
  "metadata_unsafe",
] as const;

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const UnsafeTextPattern = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const boundedSafeString = (maxLength: number, minLength = 0): z.ZodString =>
  z.string().min(minLength).max(maxLength).refine((value) => !UnsafeTextPattern.test(value), {
    message: "text contains prohibited control or bidi characters",
  });

const AcceptedStatusUpdateSchema = z.object({
  accepted: z.literal(true),
  blocking_reasons: z.array(z.string()),
  expected_state_revision: z.number().int().nonnegative().optional(),
  operation: z.enum(["initial_decision", "projection_refresh"]),
  projection_path: z.string().min(1),
  projection: AcceptedResultProjectionV2Schema,
  projection_object_sha256: Sha256Schema,
  projection_sha256: Sha256Schema,
  previous_projection_object_sha256: Sha256Schema.optional(),
  raw_bundle_sha256: Sha256Schema,
  reason: boundedSafeString(300, 1),
  schema_version: z.literal(STATUS_UPDATE_SCHEMA_VERSION),
  status: z.literal("accepted"),
  validated_at: z.iso.datetime(),
  validator_commit: z.string().nullable().optional(),
  validator_version: z.string().min(1),
  maintainer_attestation: z.object({
    coding_receipt_sha256: Sha256Schema,
    decision: z.enum(["verified", "not_verified"]),
    maintainer_key_id: z.string().min(1).max(120),
  }).optional(),
}).strict();

const RejectedStatusUpdateSchema = z.object({
  accepted: z.literal(false),
  operation: z.literal("initial_decision"),
  raw_bundle_sha256: Sha256Schema,
  reason_code: z.enum(REJECTION_REASON_CODES),
  reason_detail: boundedSafeString(300, 1).optional(),
  status: z.literal("rejected"),
  validated_at: z.iso.datetime(),
  validator_commit: boundedSafeString(120, 1).nullable().optional(),
  validator_version: boundedSafeString(120, 1),
}).strict();

export const StatusUpdateSchema = z.discriminatedUnion("status", [
  AcceptedStatusUpdateSchema,
  RejectedStatusUpdateSchema,
]).superRefine((update, context) => {
  if (update.status !== "accepted") return;
  const hasExpectedRevision = update.expected_state_revision !== undefined;
  const hasPreviousProjection = update.previous_projection_object_sha256 !== undefined;
  if (update.operation === "projection_refresh" && (!hasExpectedRevision || !hasPreviousProjection)) {
    context.addIssue({ code: "custom", message: "projection refresh concurrency guards are required" });
  }
  if (update.operation === "initial_decision" && (hasExpectedRevision || hasPreviousProjection)) {
    context.addIssue({ code: "custom", message: "initial decision cannot include refresh concurrency guards" });
  }
});

export type StatusUpdate = z.infer<typeof StatusUpdateSchema>;

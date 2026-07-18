import { z } from "zod";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;

function safeText(maxCodePoints: number, minCodePoints = 0) {
  return z.string().refine(
    (value) => [...value].length >= minCodePoints && [...value].length <= maxCodePoints,
    `must contain ${minCodePoints}-${maxCodePoints} code points`,
  ).refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}

const OptionalShaSchema = z.string().regex(SHA256_RE).nullable().optional();
const HistoryItemSchema = z.object({
  actor: safeText(80, 1),
  created_at: safeText(40, 1),
  reason: safeText(300, 1).optional(),
  to_status: safeText(40, 1),
}).strict().readonly();

export const SubmissionStatusSchema = z.object({
  bundle_schema_version: safeText(140, 1).nullable().optional(),
  community_model_group_id: safeText(140, 1).nullable().optional(),
  declared_model_slug: safeText(120, 1).nullable().optional(),
  duplicate_of: safeText(140, 1).nullable().optional(),
  expires_at: safeText(40, 1).nullable().optional(),
  held_for_review: z.boolean().optional(),
  history: z.array(HistoryItemSchema).max(100).optional(),
  origin: safeText(40, 1).nullable().optional(),
  projection_object_sha256: OptionalShaSchema,
  projection_sha256: OptionalShaSchema,
  publish_state: z.enum(["hidden", "preview", "published"]),
  raw_bundle_sha256: OptionalShaSchema,
  raw_bundle_size_bytes: z.number().int().nonnegative().nullable().optional(),
  reason_code: safeText(32, 1).nullable().optional(),
  status: safeText(40, 1),
  status_reason: safeText(300, 1).nullable().optional(),
  submission_id: safeText(140, 1),
  suite_release_id: safeText(140, 1).nullable().optional(),
  submitter_display_name: safeText(80, 1).nullable().optional(),
  tier: safeText(32, 1).nullable().optional(),
  trust_label: safeText(32, 1).nullable().optional(),
}).strict().readonly();

export type SubmissionStatus = z.infer<typeof SubmissionStatusSchema>;
export type HistoryItem = z.infer<typeof HistoryItemSchema>;

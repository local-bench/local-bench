import { z } from "zod";
import { statusCopy } from "@/app/submission/status-copy";
import type { CommunityBoardRow } from "@/lib/community-data";
import { trustTierLabel } from "@/lib/community-live";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const ISO_INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u;
const GROUP_ID_RE = /^community-group:[0-9a-f]{32}$/u;

function safeText(maxCodePoints: number, minCodePoints = 0) {
  return z.string().refine(
    (value) => [...value].length >= minCodePoints && [...value].length <= maxCodePoints,
    `must contain ${minCodePoints}-${maxCodePoints} code points`,
  ).refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}

const InstantSchema = safeText(40, 20).regex(ISO_INSTANT_RE)
  .refine((value) => !Number.isNaN(Date.parse(value)), "must be an ISO instant");
const CursorSchema = safeText(512, 1);
const ReasonCodeSchema = safeText(32, 1);

const LifecycleRowSchema = z.object({
  community_model_group_id: safeText(140, 1).regex(GROUP_ID_RE).nullable(),
  declared_model_slug: safeText(120, 1).nullable(),
  held_for_review: z.boolean(),
  publish_state: z.enum(["hidden", "preview", "published"]),
  reason_code: ReasonCodeSchema.nullable(),
  status: safeText(40, 1),
  submission_id: safeText(140, 1),
  submitter_display_name: safeText(80, 1).nullable(),
  timestamps: z.object({
    published_at: InstantSchema.nullable(),
    submitted_at: InstantSchema,
    updated_at: InstantSchema,
  }).strict().readonly(),
}).strict().readonly();

const LifecyclePageSchema = z.object({
  next_cursor: CursorSchema.nullable(),
  schema_version: z.literal("localbench.submission_lifecycle_list.v1"),
  submissions: z.array(LifecycleRowSchema).max(50).readonly(),
}).strict().readonly();

export type SubmissionLifecycleRow = z.infer<typeof LifecycleRowSchema>;
export type SubmissionLifecyclePage = {
  readonly nextCursor: string | null;
  readonly submissions: readonly SubmissionLifecycleRow[];
};

export type SubmissionDisplayRow = {
  readonly communityDetailPath: string | null;
  readonly modelLabel: string;
  readonly reasonLabel: string | null;
  readonly stateLabel: string;
  readonly submissionId: string;
  readonly submittedAt: string;
  readonly submitterLabel: string;
  readonly tierLabel: string | null;
  readonly trustLabel: string | null;
};

const REASON_CODE_LABELS: Readonly<Record<string, string>> = {
  artifact_mismatch: "Artifact mismatch",
  duplicate_submission: "Duplicate submission",
  invalid_bundle: "Invalid bundle",
  policy_violation: "Policy violation",
  unsafe_metadata: "Unsafe metadata",
  verification_failed: "Verification failed",
};

export function parseSubmissionLifecyclePage(value: unknown): SubmissionLifecyclePage | null {
  const parsed = LifecyclePageSchema.safeParse(value);
  return parsed.success
    ? { nextCursor: parsed.data.next_cursor, submissions: parsed.data.submissions }
    : null;
}

export function reasonCodeLabel(reasonCode: string): string {
  return REASON_CODE_LABELS[reasonCode] ?? reasonCode;
}

export function mergeSubmissionLifecycleRows(
  lifecycleRows: readonly SubmissionLifecycleRow[],
  communityRows: readonly CommunityBoardRow[],
): readonly SubmissionDisplayRow[] {
  const communityBySubmission = new Map(communityRows.map((row) => [row.submissionId, row] as const));
  return lifecycleRows.map((row) => {
    const community = communityBySubmission.get(row.submission_id);
    const trustLabel = community?.trust?.trust_label ?? null;
    return {
      communityDetailPath: community?.detailPath ?? null,
      modelLabel: community?.displayName ?? row.declared_model_slug ?? "model unavailable",
      reasonLabel: row.reason_code === null ? null : reasonCodeLabel(row.reason_code),
      stateLabel: lifecycleStateLabel(row),
      submissionId: row.submission_id,
      submittedAt: row.timestamps.submitted_at,
      submitterLabel: row.submitter_display_name
        ?? community?.submitterDisplayName
        ?? (community?.submitterKeyFingerprint ? `key:${community.submitterKeyFingerprint}` : "not provided"),
      tierLabel: trustLabel === null ? null : trustTierLabel(trustLabel),
      trustLabel,
    };
  });
}

function lifecycleStateLabel(row: SubmissionLifecycleRow): string {
  if (row.held_for_review) return "Held for review";
  if (row.publish_state === "published") return "Published";
  return statusCopy(row.status).label;
}

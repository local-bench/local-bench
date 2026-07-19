import { z } from "zod";
import { statusCopy } from "@/app/submission/status-copy";
import type { CommunityBoardRow } from "@/lib/community-data";
import { trustTierLabel } from "@/lib/community-live";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const ISO_INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u;

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
const GITHUB_LOGIN_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/u;

const LifecycleRowSchema = z.object({
  created_at: InstantSchema,
  declared_model_slug: safeText(120, 1).nullable(),
  held_for_review: z.boolean().optional(),
  published_at: InstantSchema.nullable(),
  publish_state: z.enum(["hidden", "preview", "published"]),
  reason_code: ReasonCodeSchema.nullable().optional(),
  status: safeText(40, 1),
  submission_id: safeText(140, 1),
  submitter_display_name: safeText(80, 1).nullable(),
  github_login: z.string().regex(GITHUB_LOGIN_RE).nullable().optional(),
  validated_at: InstantSchema.nullable(),
}).strict().readonly();

const LifecyclePageSchema = z.object({
  next_cursor: CursorSchema.nullable(),
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
  readonly submitterDisplayName: string | null;
  readonly submitterGithubLogin: string | null;
  readonly submitterKeyFingerprint: string | null;
  readonly tierLabel: string | null;
  readonly trustLabel: string | null;
};

const REASON_CODE_LABELS: Readonly<Record<string, string>> = {
  bundle_unreadable: "Bundle unreadable",
  identity_mismatch: "Identity mismatch",
  internal_error: "Internal error",
  item_count_mismatch: "Item count mismatch",
  manifest_invalid: "Invalid manifest",
  metadata_unsafe: "Unsafe metadata",
  rescore_failed: "Re-score failed",
  sampler_violation: "Sampler violation",
  schema_violation: "Schema violation",
  signature_invalid: "Invalid signature",
  size_violation: "Size violation",
  suite_mismatch: "Suite mismatch",
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
      reasonLabel: row.reason_code == null ? null : reasonCodeLabel(row.reason_code),
      stateLabel: lifecycleStateLabel(row),
      submissionId: row.submission_id,
      submittedAt: row.created_at,
      submitterDisplayName: row.submitter_display_name ?? community?.submitterDisplayName ?? null,
      submitterGithubLogin: row.github_login ?? community?.submitterGithubLogin ?? null,
      submitterKeyFingerprint: community?.submitterKeyFingerprint ?? null,
      tierLabel: trustLabel === null ? null : trustTierLabel(trustLabel),
      trustLabel,
    };
  });
}

function lifecycleStateLabel(row: SubmissionLifecycleRow): string {
  if (row.publish_state === "published") return "Published";
  return statusCopy(row.status).label;
}

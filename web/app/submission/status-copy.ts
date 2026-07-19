export type SubmissionStatusCopy = {
  readonly body: string;
  readonly label: string;
  readonly next: string;
  readonly tone: string;
};

export const PUBLISH_COPY = {
  hidden: "Hidden: not visible on the public board or feed.",
  preview: "Preview: visible for inspection, but not treated as fully published.",
  published: "Published: eligible for public board surfaces generated from accepted rows.",
} satisfies Record<"hidden" | "preview" | "published", string>;

const STATUS_COPY = {
  published: {
    body: "The submission validated and published to the board in the same request, attributed to the submitter.",
    label: "Published",
    next: "The row is live and ranked when complete; maintainers moderate post-hoc and can suppress rows.",
    tone: "text-bench-better",
  },
  accepted: {
    body: "A maintainer-reviewed legacy submission. Publication is still controlled separately by publish_state.",
    label: "Accepted",
    next: "If publish_state is hidden, the row is not on the board yet. Preview and published rows can be inspected publicly.",
    tone: "text-bench-better",
  },
  expired: {
    body: "The ticket expired after the upload grace period without a completed bundle.",
    label: "Expired",
    next: "Create a fresh ticket by running submit again.",
    tone: "text-bench-muted",
  },
  pending_verification: {
    body: "The bundle uploaded successfully and is waiting for automated contract validation.",
    label: "Validating",
    next: "No action is needed unless the service reports a contract problem.",
    tone: "text-bench-warn",
  },
  rejected: {
    body: "The verifier or maintainer rejected the submission under the current submission contract.",
    label: "Rejected",
    next: "Fix the reported issue and submit a new bundle.",
    tone: "text-bench-worse",
  },
  suppressed: {
    body: "The row was removed by a maintainer for abuse, integrity, or safety reasons.",
    label: "Suppressed",
    next: "Suppressed rows are hidden from public board surfaces.",
    tone: "text-bench-worse",
  },
  ticketed: {
    body: "A one-use upload ticket exists, but the bundle has not been completed yet.",
    label: "Ticketed",
    next: "The CLI should upload the bundle and complete the submission automatically.",
    tone: "text-bench-accent",
  },
  withdrawn: {
    body: "The accepted row was hidden after a submitter removal request.",
    label: "Withdrawn",
    next: "Withdrawn rows stay hidden while the submission record remains auditable.",
    tone: "text-bench-muted",
  },
} satisfies Record<string, SubmissionStatusCopy>;

const STATUS_COPY_BY_STATUS: Record<string, SubmissionStatusCopy> = STATUS_COPY;

export function statusCopy(status: string): SubmissionStatusCopy {
  return (
    STATUS_COPY_BY_STATUS[status] ?? {
      body: "This row uses a legacy or unknown server status.",
      label: status,
      next: "The maintainer may need to inspect the submission record directly.",
      tone: "text-bench-muted",
    }
  );
}

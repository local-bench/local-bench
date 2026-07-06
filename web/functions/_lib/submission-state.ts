export const SUBMISSION_STATUSES = [
  "ticketed",
  "pending_verification",
  "accepted",
  "rejected",
  "withdrawn",
  "suppressed",
  "expired",
] as const;

export type SubmissionStatus = (typeof SUBMISSION_STATUSES)[number];

export const ALLOWED_SUBMISSION_TRANSITIONS = {
  accepted: ["withdrawn", "suppressed"],
  expired: [],
  pending_verification: ["accepted", "rejected"],
  rejected: [],
  suppressed: [],
  ticketed: ["pending_verification", "expired"],
  withdrawn: [],
} as const satisfies Record<SubmissionStatus, readonly SubmissionStatus[]>;

export class InvalidTransitionError extends Error {
  readonly code = "invalid_transition";
  override readonly name = "InvalidTransitionError";

  constructor(
    readonly from: string,
    readonly to: string,
  ) {
    super(`invalid submission status transition: ${from} -> ${to}`);
  }
}

export function isSubmissionStatus(value: string): value is SubmissionStatus {
  return SUBMISSION_STATUSES.some((status) => status === value);
}

export function assertTransition(from: string, to: string): asserts to is SubmissionStatus {
  if (!isSubmissionStatus(from) || !isSubmissionStatus(to)) {
    throw new InvalidTransitionError(from, to);
  }
  if (!ALLOWED_SUBMISSION_TRANSITIONS[from].some((allowed) => allowed === to)) {
    throw new InvalidTransitionError(from, to);
  }
}

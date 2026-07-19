export type PendingTicket = {
  readonly model_label: string;
  readonly position: number;
  readonly queued_at: string;
  readonly submission_id: string;
  readonly suite_release_id: string | null;
};

export type QueuePayload = {
  readonly cohort_cap: number;
  readonly submissions: readonly PendingTicket[];
  readonly total_pending: number;
};

export function parseQueue(value: unknown): QueuePayload {
  if (!isRecord(value)) throw new Error("invalid pending queue payload");
  const cohortCap = value["cohort_cap"];
  const totalPending = value["total_pending"];
  const rawSubmissions = value["submissions"];
  if (
    typeof cohortCap !== "number"
    || !Number.isInteger(cohortCap)
    || typeof totalPending !== "number"
    || !Number.isInteger(totalPending)
    || !Array.isArray(rawSubmissions)
  ) throw new Error("invalid pending queue payload");
  const submissions = rawSubmissions.map(parseTicket);
  return { cohort_cap: cohortCap, submissions, total_pending: totalPending };
}

function parseTicket(value: unknown): PendingTicket {
  if (!isRecord(value)) throw new Error("invalid pending queue ticket");
  const position = value["position"];
  if (
    typeof position !== "number"
    || !Number.isInteger(position)
    || typeof value["model_label"] !== "string"
    || typeof value["queued_at"] !== "string"
    || typeof value["submission_id"] !== "string"
  ) throw new Error("invalid pending queue ticket");
  return {
    model_label: value["model_label"],
    position,
    queued_at: value["queued_at"],
    submission_id: value["submission_id"],
    suite_release_id: nullableString(value["suite_release_id"]),
  };
}

function nullableString(value: unknown): string | null {
  if (value === null || typeof value === "string") return value;
  throw new Error("queue field must be a string or null");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

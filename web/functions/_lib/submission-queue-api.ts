import type { SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { countPendingVerification, listPendingVerificationQueue } from "./submission-store";

export const PENDING_VERIFICATION_COHORT_CAP = 5;

export async function handlePendingVerificationQueue(env: SubmissionApiEnv): Promise<Response> {
  const [totalPending, rows] = await Promise.all([
    countPendingVerification(env),
    listPendingVerificationQueue(env, PENDING_VERIFICATION_COHORT_CAP),
  ]);
  return jsonResponse(200, {
    cohort_cap: PENDING_VERIFICATION_COHORT_CAP,
    policy: "fifo_exact_gguf_maintainer_agentic_verification",
    submissions: rows.map((row, index) => ({
      declared_model_slug: row.declared_model_slug,
      position: index + 1,
      queued_at: d1TimestampToIso(row.queued_at),
      submission_id: row.submission_id,
      submitter_display_name: row.submitter_display_name,
      suite_release_id: row.suite_release_id,
    })),
    total_pending: totalPending,
  });
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.slice(0, 10)}T${value.slice(11)}Z`
    : value;
}

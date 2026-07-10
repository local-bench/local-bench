import { handlePendingVerificationQueue } from "../../_lib/submission-queue-api";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

export function onRequestGet(context: { readonly env: SubmissionApiEnv }): Promise<Response> {
  return handlePendingVerificationQueue(context.env);
}

import { handleSuppressSubmission } from "../../../../_lib/submission-moderation-api";
import type { SubmissionApiEnv } from "../../../../_lib/submission-api";

export function onRequestPost(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleSuppressSubmission(context.request, context.env, context.params);
}

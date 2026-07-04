import { handleApplyVerificationUpdate, type SubmissionApiEnv } from "../../../../_lib/submission-api";

export function onRequestPost(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleApplyVerificationUpdate(context.request, context.env, context.params);
}

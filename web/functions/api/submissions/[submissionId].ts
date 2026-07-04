import { handleSubmissionStatus, type SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
}): Promise<Response> {
  return handleSubmissionStatus(context.env, context.params);
}

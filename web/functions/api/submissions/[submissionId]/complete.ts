import { handleFinalizeSubmission, type SubmissionApiEnv } from "../../../_lib/submission-api";

export function onRequestPost(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
  readonly waitUntil?: (task: Promise<unknown>) => void;
}): Promise<Response> {
  return handleFinalizeSubmission(context.request, context.env, context.params, context.waitUntil === undefined
    ? {}
    : { waitUntil: context.waitUntil });
}

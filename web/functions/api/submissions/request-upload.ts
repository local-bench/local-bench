import { handleRequestUploadTarget, type SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleRequestUploadTarget(context.request, context.env);
}

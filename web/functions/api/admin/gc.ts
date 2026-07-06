import { handleGcSubmissions } from "../../_lib/submission-gc-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleGcSubmissions(context.request, context.env);
}

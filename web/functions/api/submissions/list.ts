import { handleSubmissionLifecycleList } from "../../_lib/submission-lifecycle-api";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleSubmissionLifecycleList(context.request, context.env);
}

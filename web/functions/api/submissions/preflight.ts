import { handlePublishabilityPreflight } from "../../_lib/submission-preflight-api";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handlePublishabilityPreflight(context.request, context.env);
}

import { handleGithubDeviceStart } from "../../../../_lib/github-oauth-api";
import type { SubmissionApiEnv } from "../../../../_lib/submission-contracts";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleGithubDeviceStart(context.request, context.env);
}

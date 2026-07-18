import { handleGithubCallback } from "../../../_lib/github-oauth-api";
import type { SubmissionApiEnv } from "../../../_lib/submission-contracts";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleGithubCallback(context.request, context.env);
}

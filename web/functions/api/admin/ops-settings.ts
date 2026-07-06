import { handleGetOpsSettings, handleUpdateOpsSettings } from "../../_lib/submission-ops-settings-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleGetOpsSettings(context.request, context.env);
}

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleUpdateOpsSettings(context.request, context.env);
}

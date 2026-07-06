import { handlePublishBatch } from "../../_lib/submission-zt1-admin-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handlePublishBatch(context.request, context.env);
}

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handlePublishBatch(context.request, context.env);
}

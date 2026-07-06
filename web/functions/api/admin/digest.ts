import { handleDigest } from "../../_lib/submission-zt1-admin-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleDigest(context.request, context.env);
}

import { handleAdminListSubmissions, type SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleAdminListSubmissions(context.request, context.env);
}

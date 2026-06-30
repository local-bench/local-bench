import { handleIssueSubmissionTicket, type SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleIssueSubmissionTicket(context.request, context.env);
}

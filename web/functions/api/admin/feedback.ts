import { handleAdminListFeedback, type FeedbackApiEnv } from "../../_lib/feedback-api";

export function onRequestGet(context: { readonly env: FeedbackApiEnv; readonly request: Request }): Promise<Response> {
  return handleAdminListFeedback(context.request, context.env);
}

import { handleAdminMarkFeedbackRead, type FeedbackApiEnv } from "../../../../_lib/feedback-api";

export function onRequestPost(context: {
  readonly env: FeedbackApiEnv;
  readonly params: { readonly id?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleAdminMarkFeedbackRead(context.request, context.env, context.params);
}

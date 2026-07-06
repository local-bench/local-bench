import { handleCreateFeedback, type FeedbackApiEnv } from "../_lib/feedback-api";

export function onRequestPost(context: {
  readonly env: FeedbackApiEnv;
  readonly request: Request;
  readonly waitUntil?: (promise: Promise<unknown>) => void;
}): Promise<Response> {
  const waitUntil = context.waitUntil === undefined ? undefined : { waitUntil: context.waitUntil };
  return handleCreateFeedback(context.request, context.env, waitUntil);
}

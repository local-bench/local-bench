import { handleAcceptedFeed } from "../../_lib/submission-feed-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: { readonly env: SubmissionApiEnv }): Promise<Response> {
  return handleAcceptedFeed(context.env);
}

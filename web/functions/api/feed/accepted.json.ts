import { handleAcceptedFeed } from "../../_lib/submission-feed-api";
import type { SubmissionApiEnv } from "../../_lib/submission-api";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request?: Request }): Promise<Response> {
  return handleAcceptedFeed(context.request ?? new Request("https://local-bench.ai/api/feed/accepted.json"), context.env);
}

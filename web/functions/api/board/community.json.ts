import { handleCommunityLiveBoard } from "../../_lib/community-live-board";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

export function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleCommunityLiveBoard(context.request, context.env);
}

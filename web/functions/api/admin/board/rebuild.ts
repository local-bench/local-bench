import { handleAdminCommunityBoardRebuild } from "../../../_lib/community-live-board";
import type { SubmissionApiEnv } from "../../../_lib/submission-contracts";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleAdminCommunityBoardRebuild(context.request, context.env);
}

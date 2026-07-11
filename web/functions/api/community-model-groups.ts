import { handleCreateCommunityModelGroup } from "../_lib/community-model-groups";
import type { SubmissionApiEnv } from "../_lib/submission-contracts";

export async function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleCreateCommunityModelGroup(context.request, context.env);
}

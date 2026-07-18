import { handleUpdateSubmissionDisplayName } from "../../../../_lib/submission-admin-artifacts-api";
import type { SubmissionApiEnv } from "../../../../_lib/submission-contracts";

export function onRequestPost(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleUpdateSubmissionDisplayName(context.request, context.env, context.params);
}

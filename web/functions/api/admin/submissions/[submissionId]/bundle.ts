import { handleDownloadSubmissionBundle } from "../../../../_lib/submission-admin-artifacts-api";
import type { SubmissionApiEnv } from "../../../../_lib/submission-contracts";

export function onRequestGet(context: {
  readonly env: SubmissionApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleDownloadSubmissionBundle(context.request, context.env, context.params);
}

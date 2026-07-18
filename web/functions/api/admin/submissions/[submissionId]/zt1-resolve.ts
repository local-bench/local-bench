import type { RouteParams, SubmissionApiEnv } from "../../../../_lib/submission-contracts";
import { handleZt1Resolve } from "../../../../_lib/submission-zt1-resolve-api";

export const onRequestPost = async (context: {
  readonly env: SubmissionApiEnv;
  readonly params: RouteParams;
  readonly request: Request;
}): Promise<Response> => handleZt1Resolve(context.request, context.env, context.params);

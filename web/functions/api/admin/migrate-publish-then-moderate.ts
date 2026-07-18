import { handleMigratePublishThenModerate } from "../../_lib/submission-ptm-migration-api";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

export function onRequestPost(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleMigratePublishThenModerate(context.request, context.env);
}

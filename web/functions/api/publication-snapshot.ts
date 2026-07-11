import { handleServeActivePublicationSnapshot } from "../_lib/publication-snapshot";
import type { SubmissionApiEnv } from "../_lib/submission-contracts";

export async function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  return handleServeActivePublicationSnapshot(context.request, context.env);
}

import { handleSubmissionStatus, type ApiEnv } from "../../_lib/api";

export function onRequestGet(context: {
  readonly env: ApiEnv;
  readonly params: { readonly submissionId?: string };
}): Promise<Response> {
  return handleSubmissionStatus(context.env, context.params);
}

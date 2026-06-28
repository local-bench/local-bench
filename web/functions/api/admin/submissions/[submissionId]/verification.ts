import { handleAdminVerificationResult, type ApiEnv } from "../../../../_lib/api";

export function onRequestPost(context: {
  readonly env: ApiEnv;
  readonly params: { readonly submissionId?: string };
  readonly request: Request;
}): Promise<Response> {
  return handleAdminVerificationResult(context.request, context.env, context.params);
}

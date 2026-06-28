import { handleCreateTicket, type ApiEnv } from "../../_lib/api";

export function onRequestPost(context: { readonly env: ApiEnv; readonly request: Request }): Promise<Response> {
  return handleCreateTicket(context.request, context.env);
}

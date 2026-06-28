import { handleAdminListSubmissions, type ApiEnv } from "../../_lib/api";

export function onRequestGet(context: { readonly env: ApiEnv; readonly request: Request }): Promise<Response> {
  return handleAdminListSubmissions(context.request, context.env);
}

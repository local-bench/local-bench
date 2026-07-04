import { handleSuites, type ApiEnv } from "../_lib/api";

export function onRequestGet(context: { readonly env: ApiEnv }): Response {
  return handleSuites(context.env);
}

import { handleHealth, type ApiEnv } from "../_lib/api";

export function onRequestGet(context: { readonly env: ApiEnv }): Response {
  return handleHealth(context.env);
}

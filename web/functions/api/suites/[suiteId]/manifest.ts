import { handleSuiteManifest, type ApiEnv } from "../../../_lib/api";

type Context = {
  readonly env: ApiEnv;
  readonly params: { readonly suiteId?: string };
  readonly request: Request;
};

export function onRequestGet(context: Context): Response {
  return handleSuiteManifest(context.env, new URL(context.request.url), context.params);
}

import {
  handleActivatePublicationSnapshot,
  handleCreatePublicationSnapshot,
  handleExportPublicationSnapshot,
} from "../../_lib/publication-snapshot";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";

type Context = { readonly env: SubmissionApiEnv; readonly request: Request };

export async function onRequestGet(context: Context): Promise<Response> {
  return handleExportPublicationSnapshot(context.request, context.env);
}

export async function onRequestPost(context: Context): Promise<Response> {
  const action = new URL(context.request.url).searchParams.get("action");
  return action === "activate"
    ? handleActivatePublicationSnapshot(context.request, context.env)
    : handleCreatePublicationSnapshot(context.request, context.env);
}

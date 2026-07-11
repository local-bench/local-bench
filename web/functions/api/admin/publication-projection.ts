import { adminBlocked, jsonResponse } from "../../_lib/submission-api-support";
import { sha256Hex } from "../../_lib/submission-canonical";
import type { SubmissionApiEnv } from "../../_lib/submission-contracts";
import { projectionKey } from "../../_lib/submission-storage";

export async function onRequestGet(context: { readonly env: SubmissionApiEnv; readonly request: Request }): Promise<Response> {
  const blocked = adminBlocked(context.request, context.env);
  if (blocked !== null) return blocked;
  const sha256 = new URL(context.request.url).searchParams.get("sha256");
  if (sha256 === null || !/^[0-9a-f]{64}$/.test(sha256)) {
    return jsonResponse(400, { code: "invalid_projection_sha", error: "sha256 is required" });
  }
  const object = await context.env.SUBMISSIONS.get(projectionKey(sha256));
  if (object === null) return jsonResponse(404, { code: "projection_not_found", error: "projection object not found" });
  const bytes = await new Response(object.body).text();
  if (await sha256Hex(bytes) !== sha256) throw new Error("stored projection object hash mismatch");
  return new Response(bytes, { headers: { "content-type": "application/json; charset=utf-8" }, status: 200 });
}

import { DisplayNameUpdateSchema, type RouteParams, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, authorizeValidatorRoute, jsonResponse, routeRow } from "./submission-api-support";
import { rawBundleKey } from "./submission-storage";
import { publicSubmission, recordSubmissionTransition, rowBySubmissionId } from "./submission-store";

export async function handleDownloadSubmissionBundle(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const auth = authorizeValidatorRoute(request, env);
  if (auth.kind === "blocked") return auth.response;
  const row = await routeRow(env, params);
  if (row.kind !== "ok") return row.response;
  const object = await env.SUBMISSIONS.get(rawBundleKey(row.value.raw_bundle_sha256));
  if (object === null) {
    return jsonResponse(404, { code: "raw_bundle_not_found", error: "raw submission bundle not found" });
  }
  return new Response(object.body, {
    headers: { "cache-control": "no-store", "content-type": "application/json" },
    status: 200,
  });
}

export async function handleUpdateSubmissionDisplayName(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  const row = await routeRow(env, params);
  if (row.kind !== "ok") return row.response;
  const parsed = DisplayNameUpdateSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_display_name", error: "submitter display name is invalid" });
  }
  await env.DB.prepare("update submissions set submitter_display_name = ? where submission_id = ?")
    .bind(parsed.data.display_name, row.value.submission_id)
    .run();
  await recordSubmissionTransition(env, {
    actor: "maintainer",
    fromStatus: row.value.status,
    publishState: row.value.publish_state,
    reason: "submitter display name updated",
    submissionId: row.value.submission_id,
    toStatus: row.value.status,
  });
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, {
    ...(updated === null ? publicSubmission(row.value) : publicSubmission(updated)),
    submitter_display_name: parsed.data.display_name,
  });
}

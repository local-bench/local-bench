import {
  PublishStateDecisionSchema,
  StatusUpdateSchema,
  type RouteParams,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { adminBlocked, jsonResponse, logSubmissionError, routeRow } from "./submission-api-support";
import {
  applyStatusUpdate,
  listSubmissionsByStatus,
  publicSubmission,
  rowBySubmissionId,
  updatePublishState,
} from "./submission-store";

export { handleFinalizeSubmission } from "./submission-complete-api";
export { handleIssueSubmissionTicket } from "./submission-ticket-api";
export { handleRequestUploadTarget } from "./submission-upload-api";
export type { SubmissionApiEnv } from "./submission-contracts";

export async function handleSubmissionStatus(env: SubmissionApiEnv, params: RouteParams): Promise<Response> {
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  return jsonResponse(200, publicSubmission(row.value));
}

export async function handleAdminListSubmissions(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const url = new URL(request.url);
  const status = url.searchParams.get("status") ?? "pending_verification";
  const requestedLimit = Number(url.searchParams.get("limit") ?? "20");
  const limit = Number.isFinite(requestedLimit) ? Math.min(Math.max(Math.floor(requestedLimit), 1), 100) : 20;
  const rows = await listSubmissionsByStatus(env, status, limit);
  return jsonResponse(200, { submissions: rows.map((row) => publicSubmission(row)) });
}

export async function handleApplyVerificationUpdate(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  const parsed = StatusUpdateSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_status_update", error: "invalid verifier status update" });
  }
  if (row.value.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    return jsonResponse(409, { code: "bundle_sha_mismatch", error: "status update does not match submission bundle" });
  }
  try {
    await applyStatusUpdate(env, row.value.submission_id, parsed.data);
    const updated = await rowBySubmissionId(env, row.value.submission_id);
    return jsonResponse(200, publicSubmission(updated ?? row.value));
  } catch (error) {
    logSubmissionError("submission_verification_update_failed", {
      error,
      leg: "apply_status_update",
      route: "POST /api/admin/submissions/:submissionId/verification",
      submission_id: row.value.submission_id,
    });
    return jsonResponse(500, {
      code: "submission_verification_update_failed",
      error: "submission verification update failed",
    });
  }
}

export async function handlePublishStateDecision(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  const parsed = PublishStateDecisionSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_publish_decision", error: "invalid publish_state decision" });
  }
  await updatePublishState(env, row.value.submission_id, parsed.data.publish_state);
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, publicSubmission(updated ?? row.value));
}

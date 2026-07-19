import {
  CompleteRequestSchema,
  MAX_UPLOAD_BYTES,
  type RouteParams,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { jsonResponse, logSubmissionError, routeRow } from "./submission-api-support";
import { isSyntaxError, reject, ticketExpired } from "./submission-api-common";
import { rebuildCommunityLiveBoard } from "./community-live-board";
import { persistProjectionAndReference } from "./publication-storage";
import { publishProjectionRejection, type PublishProjectionRejection } from "./submission-publish-validation";
import { validateSubmittedProjection } from "./submission-projection-validation";
import { rawBundleKey, rawBundleMetadata, verifyRawBundle } from "./submission-storage";
import {
  publicSubmission,
  publishSubmittedSubmission,
  rejectSubmittedSubmission,
  rowBySubmissionId,
} from "./submission-store";

export async function handleFinalizeSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  if (row.value.status === "published") {
    return jsonResponse(200, publicSubmission(row.value));
  }
  if (row.value.status !== "ticketed" || row.value.uploaded_at !== null) {
    return jsonResponse(409, { code: "submission_not_ticketed", error: "submission ticket is already consumed" });
  }
  if (ticketExpired(row.value.status, row.value.expires_at)) {
    return reject(410, "ticket_expired", row.value.origin, "POST /api/submissions/:submissionId/complete", {
      code: "ticket_expired",
      error: "submission ticket expired",
    }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
  }
  let requestBody: unknown;
  try {
    requestBody = await request.json();
  } catch (error) {
    if (isSyntaxError(error)) {
      return rejectComplete(env, row.value.submission_id, "schema_violation", 400);
    }
    throw error;
  }
  const parsed = CompleteRequestSchema.safeParse(requestBody);
  if (!parsed.success) {
    return rejectComplete(env, row.value.submission_id, "schema_violation", 400);
  }
  if (row.value.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
    return rejectComplete(env, row.value.submission_id, "schema_violation", 409);
  }
  try {
    const metadata = await rawBundleMetadata(env, parsed.data.raw_bundle_sha256);
    if (metadata.kind !== "ok") {
      return jsonResponse(metadata.status, { code: metadata.code, error: metadata.error });
    }
    if (metadata.size !== null && metadata.size > MAX_UPLOAD_BYTES) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return reject(413, "bundle_too_large", row.value.origin, "POST /api/submissions/:submissionId/complete", {
        code: "bundle_too_large",
        error: "uploaded bundle exceeds the server upload limit",
      }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
    }
    const verification = await verifyRawBundle(env, parsed.data.raw_bundle_sha256);
    if (verification.kind !== "ok") {
      if (verification.code !== "raw_bundle_missing") {
        await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      }
      if (verification.status === 413) {
        return reject(413, verification.code, row.value.origin, "POST /api/submissions/:submissionId/complete", {
          code: verification.code,
          error: verification.error,
        }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
      }
      return jsonResponse(verification.status, { code: verification.code, error: verification.error });
    }
    const publishRejection = publishProjectionRejection(parsed.data.accepted_result_projection, row.value);
    if (publishRejection !== null) {
      return rejectComplete(
        env,
        row.value.submission_id,
        publishRejection,
        publishRejection === "incomplete_run" ? 422 : 409,
      );
    }
    const projection = await validateSubmittedProjection(parsed.data.accepted_result_projection, row.value);
    if (projection.kind === "invalid") {
      return rejectComplete(env, row.value.submission_id, "schema_violation", 409);
    }
    await persistProjectionAndReference(
      env,
      projection.objectSha256,
      projection.canonicalBytes,
      (projectionR2Key) => publishSubmittedSubmission(
        env,
        row.value.submission_id,
        verification.sizeBytes,
        parsed.data.accepted_result_projection,
        projection.objectSha256,
        projectionR2Key,
      ),
    );
    await rebuildCommunityLiveBoard(env);
    const updated = await rowBySubmissionId(env, row.value.submission_id);
    return jsonResponse(200, publicSubmission(updated ?? row.value));
  } catch (error) {
    logSubmissionError("submission_finalize_failed", {
      error,
      leg: "publish_submitted_projection",
      route: "POST /api/submissions/:submissionId/complete",
      submission_id: row.value.submission_id,
    });
    return jsonResponse(500, { code: "submission_finalize_failed", error: "submission finalization failed" });
  }
}

async function rejectComplete(
  env: SubmissionApiEnv,
  submissionId: string,
  reason: PublishProjectionRejection,
  status: number,
): Promise<Response> {
  const current = await rowBySubmissionId(env, submissionId);
  if (current === null) {
    return jsonResponse(404, { code: "unknown_submission", error: "unknown submission" });
  }
  if (current.status === "ticketed") {
    await rejectSubmittedSubmission(env, submissionId, reason);
  }
  const updated = await rowBySubmissionId(env, submissionId);
  return jsonResponse(status, {
    code: reason,
    error: reason === "incomplete_run" ? "all six headline axes must be measured" : "submission projection is invalid",
    status: updated?.status ?? current.status,
    submission_id: submissionId,
  });
}

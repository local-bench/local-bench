import {
  CompleteRequestSchema,
  MAX_UPLOAD_BYTES,
  UploadCapabilitySchema,
  type RouteParams,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { jsonResponse, logSubmissionError, routeRow } from "./submission-api-support";
import { isRecord, reject, ticketExpired } from "./submission-api-common";
import { completionRateLimit, readCompletionBody } from "./submission-complete-guard";
import { rebuildCommunityLiveBoard } from "./community-live-board";
import { persistProjectionAndReference } from "./publication-storage";
import { publishProjectionRejection, type PublishProjectionRejection } from "./submission-publish-validation";
import { validateSubmittedProjection } from "./submission-projection-validation";
import { sha256Hex } from "./submission-canonical";
import { rawBundleKey, rawBundleMetadata, verifyRawBundle } from "./submission-storage";
import {
  publicSubmission,
  publishSubmittedSubmission,
  rejectSubmittedSubmission,
  rowBySubmissionId,
  ticketEnvelopeFromRow,
} from "./submission-store";

export async function handleFinalizeSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
  context: { readonly waitUntil?: (task: Promise<unknown>) => void } = {},
): Promise<Response> {
  const requestBody = await readCompletionBody(request);
  if (requestBody.kind === "too_large") {
    return jsonResponse(413, { code: "completion_body_too_large", error: "completion request body is too large" });
  }
  if (requestBody.kind === "invalid") {
    return invalidCompleteRequest();
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  const capability = isRecord(requestBody.value)
    ? UploadCapabilitySchema.safeParse(requestBody.value["upload_capability"])
    : { success: false } as const;
  if (
    !capability.success ||
    row.value.upload_capability_sha256 === null ||
    await sha256Hex(capability.data) !== row.value.upload_capability_sha256
  ) {
    return jsonResponse(403, { code: "upload_capability_invalid", error: "upload capability is invalid" });
  }
  const limited = await completionRateLimit(request, env, row.value);
  if (limited !== null) return limited;
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
  const parsed = CompleteRequestSchema.safeParse(requestBody.value);
  if (!parsed.success) {
    return rejectComplete(env, row.value.submission_id, "schema_violation", 400);
  }
  if (row.value.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
    return rejectComplete(env, row.value.submission_id, "schema_violation", 409);
  }
  try {
    const ticketUploadLimit = ticketEnvelopeFromRow(row.value)?.max_upload_bytes ?? MAX_UPLOAD_BYTES;
    const metadata = await rawBundleMetadata(env, parsed.data.raw_bundle_sha256);
    if (metadata.kind !== "ok") {
      return jsonResponse(metadata.status, { code: metadata.code, error: metadata.error });
    }
    if (metadata.size !== null && metadata.size > MAX_UPLOAD_BYTES) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return rejectComplete(env, row.value.submission_id, "bundle_too_large", 413);
    }
    if (metadata.size !== null && metadata.size > ticketUploadLimit) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return rejectComplete(env, row.value.submission_id, "upload_exceeds_ticket_limit", 413);
    }
    if (metadata.size !== null && metadata.size !== row.value.upload_declared_size_bytes) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return rejectComplete(env, row.value.submission_id, "upload_size_mismatch", 413);
    }
    const verification = await verifyRawBundle(env, parsed.data.raw_bundle_sha256);
    if (verification.kind !== "ok") {
      if (verification.code !== "raw_bundle_missing") {
        await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      }
      if (verification.status === 413) {
        return rejectComplete(env, row.value.submission_id, "bundle_too_large", 413);
      }
      return jsonResponse(verification.status, { code: verification.code, error: verification.error });
    }
    if (verification.sizeBytes !== row.value.upload_declared_size_bytes) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return rejectComplete(env, row.value.submission_id, "upload_size_mismatch", 413);
    }
    if (verification.sizeBytes > ticketUploadLimit) {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      return rejectComplete(env, row.value.submission_id, "upload_exceeds_ticket_limit", 413);
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
        projection.projection,
        projection.objectSha256,
        projectionR2Key,
      ),
    );
    context.waitUntil?.(
      rebuildCommunityLiveBoard(env).catch((error) => {
        logSubmissionError("community_board_rebuild_failed", {
          error,
          leg: "post_publish_board_rebuild",
          route: "POST /api/submissions/:submissionId/complete",
          submission_id: row.value.submission_id,
        });
      }),
    );
    const updated = await rowBySubmissionId(env, row.value.submission_id);
    return jsonResponse(200, publicSubmission(updated ?? row.value));
  } catch (error) {
    const published = await rowBySubmissionId(env, row.value.submission_id);
    if (published?.status === "published") {
      return jsonResponse(200, publicSubmission(published));
    }
    const loggedError = error instanceof Error ? error : new Error(String(error));
    logSubmissionError("submission_finalize_failed", {
      error: loggedError,
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
  reason: PublishProjectionRejection | "bundle_too_large" | "upload_exceeds_ticket_limit" | "upload_size_mismatch",
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
    error: completeRejectionMessage(reason),
    status: updated?.status ?? current.status,
    submission_id: submissionId,
  });
}

function completeRejectionMessage(
  reason: PublishProjectionRejection | "bundle_too_large" | "upload_exceeds_ticket_limit" | "upload_size_mismatch",
): string {
  if (reason === "incomplete_run") return "all six headline axes must be measured";
  if (reason === "bundle_too_large") return "uploaded bundle exceeds the server upload limit";
  if (reason === "upload_exceeds_ticket_limit") return "uploaded bundle exceeds the ticket-specific byte limit";
  if (reason === "upload_size_mismatch") return "uploaded bundle size does not match the signed declaration";
  return "submission projection is invalid";
}

function invalidCompleteRequest(): Response {
  return jsonResponse(400, { code: "schema_violation", error: "submission projection is invalid" });
}

import {
  CompleteRequestSchema,
  MAX_UPLOAD_BYTES,
  type RouteParams,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { jsonResponse, logSubmissionError, routeRow } from "./submission-api-support";
import { isSyntaxError, reject, ticketExpired } from "./submission-api-common";
import { rawBundleKey, rawBundleMetadata, verifyRawBundle } from "./submission-storage";
import { markPendingVerification, publicSubmission, rowBySubmissionId } from "./submission-store";

export async function handleFinalizeSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  let requestBody: unknown;
  try {
    requestBody = await request.json();
  } catch (error) {
    if (isSyntaxError(error)) {
      return invalidCompleteRequest();
    }
    throw error;
  }
  const parsed = CompleteRequestSchema.safeParse(requestBody);
  if (!parsed.success) {
    return invalidCompleteRequest();
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  if (row.value.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
    return jsonResponse(409, { code: "bundle_sha_mismatch", error: "raw_bundle_sha256 does not match ticket" });
  }
  if (row.value.status === "pending_verification") {
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
    const admission = await markPendingVerification(
      env,
      row.value.submission_id,
      verification.sizeBytes,
    );
    if (admission.kind === "error") {
      await env.SUBMISSIONS.delete(rawBundleKey(row.value.raw_bundle_sha256));
      const status = admission.code === "submission_not_ticketed" ? 409 : 429;
      return reject(status, admission.code, row.value.origin, "POST /api/submissions/:submissionId/complete", {
        code: admission.code,
        error: admissionError(admission.code),
      }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
    }
    const updated = await rowBySubmissionId(env, row.value.submission_id);
    return jsonResponse(200, publicSubmission(updated ?? row.value));
  } catch (error) {
    logSubmissionError("submission_finalize_failed", {
      error,
      leg: "mark_pending_verification",
      route: "POST /api/submissions/:submissionId/complete",
      submission_id: row.value.submission_id,
    });
    return jsonResponse(500, { code: "submission_finalize_failed", error: "submission finalization failed" });
  }
}

function admissionError(code: string): string {
  switch (code) {
    case "pending_review_limit": return "submitter pending-review admission limit reached";
    case "global_pending_limit": return "global pending-review admission limit reached";
    default: return "submission ticket is already consumed";
  }
}

function invalidCompleteRequest(): Response {
  return jsonResponse(400, { code: "invalid_complete_request", error: "invalid upload completion request" });
}

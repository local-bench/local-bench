import {
  CompleteRequestSchema,
  MAX_UPLOAD_BYTES,
  ResultBundleSchema,
  type RouteParams,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { canonicalPayloadSha256 } from "./submission-canonical";
import { jsonResponse, logSubmissionError, routeRow, suiteMismatches } from "./submission-api-support";
import { isRecord, isSyntaxError, parseJson, reject, ticketExpired } from "./submission-api-common";
import { readRawBundle, rawBundleMetadata } from "./submission-storage";
import { validatePendingAdmission } from "./submission-semantic";
import { markPendingVerification, publicSubmission, rowByPayloadSha, rowBySubmissionId } from "./submission-store";

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
      return reject(413, "bundle_too_large", row.value.origin, "POST /api/submissions/:submissionId/complete", {
        code: "bundle_too_large",
        error: "uploaded bundle exceeds the server upload limit",
      }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
    }
    const bundleRead = await readRawBundle(env, parsed.data.raw_bundle_sha256);
    if (bundleRead.kind !== "ok") {
      return jsonResponse(bundleRead.status, { code: bundleRead.code, error: bundleRead.error });
    }
    const rawBundleSizeBytes = bundleRead.sizeBytes;
    const rawBundle = parseJson(bundleRead.text);
    const bundle = rawBundle === null ? null : ResultBundleSchema.safeParse(rawBundle);
    if (bundle === null || !bundle.success) {
      return jsonResponse(400, { code: "invalid_result_bundle", error: "uploaded bundle does not match result_bundle_v1" });
    }
    if (suiteMismatches(row.value, bundle.data)) {
      return jsonResponse(409, { code: "suite_mismatch", error: "uploaded bundle suite does not match submission ticket" });
    }
    // Owner decision 2026-07-04: community bundles may include dynamic (agentic)
    // benches. Their verdicts are carried as self-reported at rescore and rows only
    // publish after manual admin acceptance; provenance labeling happens in the
    // Python rescorer, not by rejection here.
    if (keyMismatch(row.value.submitter_id, rawBundle)) {
      return reject(409, "key_mismatch", row.value.origin, "POST /api/submissions/:submissionId/complete", {
        code: "key_mismatch",
        error: "uploaded bundle public key does not match submission ticket",
      }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
    }
    const semantic = await validatePendingAdmission(row.value, rawBundle, bundle.data);
    if (semantic.kind === "error") {
      return reject(400, semantic.code, row.value.origin, "POST /api/submissions/:submissionId/complete", {
        code: semantic.code,
        error: semantic.error,
      }, row.value.raw_bundle_sha256, row.value.submitter_id ?? undefined);
    }
    const payloadSha256 = await canonicalPayloadSha256(rawBundle);
    const duplicate = await rowByPayloadSha(env, payloadSha256);
    const duplicateOf = duplicate !== null && duplicate.submission_id !== row.value.submission_id
      ? duplicate.submission_id
      : null;
    const admission = await markPendingVerification(
      env,
      row.value.submission_id,
      bundle.data,
      rawBundleSizeBytes,
      payloadSha256,
      duplicateOf,
      semantic.modelFileSha256,
    );
    if (admission.kind === "error") {
      const status = admission.code === "model_already_pending" || admission.code === "submission_not_ticketed" ? 409 : 429;
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
    case "model_already_pending": return "this exact GGUF identity is already pending or accepted";
    default: return "submission ticket is already consumed";
  }
}

function keyMismatch(submitterId: string | null, rawBundle: unknown): boolean {
  const ticketPublicKey = publicKeyFromSubmitterId(submitterId);
  if (ticketPublicKey === null) {
    return false;
  }
  return bundlePublicKey(rawBundle) !== ticketPublicKey;
}

function bundlePublicKey(rawBundle: unknown): string | null {
  if (!isRecord(rawBundle) || !isRecord(rawBundle["signature"])) {
    return null;
  }
  const signature = rawBundle["signature"];
  return typeof signature["public_key"] === "string" ? signature["public_key"] : null;
}

function publicKeyFromSubmitterId(submitterId: string | null): string | null {
  if (submitterId === null || !submitterId.startsWith("public_key:")) {
    return null;
  }
  return submitterId.slice("public_key:".length);
}

function invalidCompleteRequest(): Response {
  return jsonResponse(400, { code: "invalid_complete_request", error: "invalid upload completion request" });
}

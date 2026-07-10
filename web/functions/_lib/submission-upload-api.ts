import { UploadTargetRequestSchema, type SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { sha256Hex } from "./submission-canonical";
import { clientIp, reject, ticketExpired } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";
import { rawBundleMetadata, signedUploadUrl } from "./submission-storage";
import { rowBySubmissionId } from "./submission-store";

const REQUEST_UPLOADS_PER_IP_PER_HOUR = 60;

export async function handleRequestUploadTarget(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const parsed = UploadTargetRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_upload_target_request", error: "invalid upload target request" });
  }
  const limit = await rateLimited(env, `request-upload:ip:${clientIp(request)}`, REQUEST_UPLOADS_PER_IP_PER_HOUR, 60 * 60);
  if (limit.limited) {
    return reject(429, "rate_limited", "community", "POST /api/submissions/request-upload", {
      code: "rate_limited",
      retry_after_seconds: limit.retryAfterSeconds,
    });
  }
  const row = await rowBySubmissionId(env, parsed.data.ticket_id);
  if (row === null || row.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    return jsonResponse(404, { code: "unknown_ticket", error: "unknown submission ticket" });
  }
  if (
    row.status !== "ticketed" ||
    row.uploaded_at !== null ||
    row.upload_capability_sha256 === null ||
    await sha256Hex(parsed.data.upload_capability) !== row.upload_capability_sha256
  ) {
    return jsonResponse(404, { code: "unknown_ticket", error: "unknown submission ticket" });
  }
  if (ticketExpired(row.status, row.expires_at)) {
    return reject(410, "ticket_expired", row.origin, "POST /api/submissions/request-upload", {
      code: "ticket_expired",
      error: "submission ticket expired",
    }, row.raw_bundle_sha256, row.submitter_id ?? undefined);
  }
  const existing = await rawBundleMetadata(env, parsed.data.raw_bundle_sha256);
  if (existing.kind === "ok") {
    return jsonResponse(409, { code: "raw_bundle_exists", error: "raw bundle object already exists" });
  }
  if (existing.code !== "raw_bundle_missing") {
    return jsonResponse(existing.status, { code: existing.code, error: existing.error });
  }
  const target = await signedUploadUrl(env, parsed.data.raw_bundle_sha256);
  if (target.kind === "disabled") {
    return jsonResponse(503, { code: "r2_signing_disabled", error: "R2 upload signing is disabled" });
  }
  return jsonResponse(200, {
    bucket: target.bucketName,
    content_sha256: parsed.data.raw_bundle_sha256,
    expires_seconds: 3600,
    method: "PUT",
    r2_key: target.r2Key,
    upload_headers: target.uploadHeaders,
    upload_url: target.uploadUrl,
  });
}

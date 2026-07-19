import {
  SUBMISSIONS_BUCKET_NAME,
  UploadTargetRequestSchema,
  type SubmissionApiEnv,
  type SubmissionRow,
} from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { sha256Hex } from "./submission-canonical";
import { clientIp, reject, ticketExpired } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";
import {
  rawBundleKey,
  rawBundleMetadata,
  signedUploadHeaders,
  signedUploadUrl,
  type SignedUploadTarget,
} from "./submission-storage";
import { rowBySubmissionId } from "./submission-store";

const REQUEST_UPLOADS_PER_IP_PER_HOUR = 60;
const DAILY_UPLOAD_BYTE_BUDGET = 8 * 1024 * 1024 * 1024;

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
  const storedTarget = uploadTargetFromRow(env, row);
  if (storedTarget !== null) {
    if (row.upload_declared_size_bytes !== parsed.data.size_bytes) {
      return jsonResponse(409, { code: "upload_size_already_declared", error: "upload size is already declared" });
    }
    return uploadTargetResponse(storedTarget, parsed.data.raw_bundle_sha256);
  }
  const existing = await rawBundleMetadata(env, parsed.data.raw_bundle_sha256);
  if (existing.kind === "ok") {
    return jsonResponse(409, { code: "raw_bundle_exists", error: "raw bundle object already exists" });
  }
  if (existing.code !== "raw_bundle_missing") {
    return jsonResponse(existing.status, { code: existing.code, error: existing.error });
  }
  const target = await signedUploadUrl(env, parsed.data.raw_bundle_sha256, parsed.data.size_bytes);
  if (target.kind === "disabled") {
    return jsonResponse(503, { code: "r2_signing_disabled", error: "R2 upload signing is disabled" });
  }
  const day = new Date().toISOString().slice(0, 10);
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowSeconds = 24 * 60 * 60;
  const windowStartSeconds = nowSeconds - (nowSeconds % windowSeconds);
  const windowStart = new Date(windowStartSeconds * 1000).toISOString();
  const retryAfterSeconds = Math.max(windowStartSeconds + windowSeconds - nowSeconds, 1);
  const budgetKey = `upload_bytes:${day}`;
  if (env.DB.batch === undefined) throw new Error("D1 batch support is required for upload target issuance");
  const results = await env.DB.batch([
    env.DB.prepare(
      `insert into rate_counters (bucket_key, window_start, count)
       select ?, ?, ? where exists (
         select 1 from submissions
         where submission_id = ? and status = 'ticketed' and uploaded_at is null and upload_target_url is null
       )
       on conflict(bucket_key) do update set
         window_start = ?,
         count = (case when rate_counters.window_start = ? then rate_counters.count else 0 end) + ?
       where (case when rate_counters.window_start = ? then rate_counters.count else 0 end) + ? <= ?`,
    ).bind(
      budgetKey,
      windowStart,
      parsed.data.size_bytes,
      row.submission_id,
      windowStart,
      windowStart,
      parsed.data.size_bytes,
      windowStart,
      parsed.data.size_bytes,
      DAILY_UPLOAD_BYTE_BUDGET,
    ),
    env.DB.prepare(
      `update submissions set upload_declared_size_bytes = ?, upload_target_url = ?
       where submission_id = ? and status = 'ticketed' and uploaded_at is null and upload_target_url is null
         and changes() = 1`,
    ).bind(
      parsed.data.size_bytes,
      target.uploadUrl,
      row.submission_id,
    ),
  ]);
  if (results[1]?.meta?.changes === 1) {
    return uploadTargetResponse(target, parsed.data.raw_bundle_sha256);
  }
  const refreshed = await rowBySubmissionId(env, row.submission_id);
  if (refreshed !== null) {
    const racedTarget = uploadTargetFromRow(env, refreshed);
    if (racedTarget !== null && refreshed.upload_declared_size_bytes === parsed.data.size_bytes) {
      return uploadTargetResponse(racedTarget, parsed.data.raw_bundle_sha256);
    }
  }
  const counter = await env.DB.prepare(
    "select count from rate_counters where bucket_key = ? and window_start = ?",
  ).bind(budgetKey, windowStart).first();
  if (
    typeof counter?.["count"] === "number" &&
    counter["count"] + parsed.data.size_bytes > DAILY_UPLOAD_BYTE_BUDGET
  ) {
    return Response.json({ code: "upload_byte_budget_exceeded", retry_after_seconds: retryAfterSeconds }, {
      headers: { "cache-control": "no-store", "retry-after": String(retryAfterSeconds) },
      status: 429,
    });
  }
  return jsonResponse(409, { code: "upload_target_conflict", error: "upload target issuance conflicted" });
}

function uploadTargetFromRow(env: SubmissionApiEnv, row: SubmissionRow): SignedUploadTarget | null {
  if (row.upload_declared_size_bytes === null || row.upload_target_url === null) return null;
  return {
    bucketName: env.R2_BUCKET_NAME ?? SUBMISSIONS_BUCKET_NAME,
    kind: "ok",
    r2Key: rawBundleKey(row.raw_bundle_sha256),
    uploadHeaders: signedUploadHeaders(row.upload_declared_size_bytes),
    uploadUrl: row.upload_target_url,
  };
}

function uploadTargetResponse(target: SignedUploadTarget, rawBundleSha256: string): Response {
  return jsonResponse(200, {
    bucket: target.bucketName,
    content_sha256: rawBundleSha256,
    expires_seconds: 3600,
    method: "PUT",
    r2_key: target.r2Key,
    upload_headers: target.uploadHeaders,
    upload_url: target.uploadUrl,
  });
}

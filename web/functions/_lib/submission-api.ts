import {
  CompleteRequestSchema,
  DEFAULT_MAX_UPLOAD_BYTES,
  DEFAULT_SUITE_MANIFEST_SHA256,
  DEFAULT_SUITE_RELEASE_ID,
  PublishStateDecisionSchema,
  RESULT_BUNDLE_SCHEMA_VERSION,
  ResultBundleSchema,
  SUBMISSION_ENVELOPE_SCHEMA_VERSION,
  StatusUpdateSchema,
  TicketRequestSchema,
  UploadTargetRequestSchema,
  type RouteParams,
  type SubmissionApiEnv,
  type SubmissionEnvelope,
  type TicketRequest,
} from "./submission-contracts";
import { readRawBundle, signedUploadUrl } from "./submission-storage";
import {
  applyStatusUpdate,
  insertTicketedSubmission,
  markPendingVerification,
  publicSubmission,
  rowByRawBundleSha,
  rowBySubmissionId,
  updatePublishState,
} from "./submission-store";

export type { SubmissionApiEnv } from "./submission-contracts";

export async function handleIssueSubmissionTicket(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const parsed = TicketRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_ticket_request", error: "invalid submission ticket request" });
  }
  const ticket = ticketEnvelope(parsed.data);
  const existing = await rowByRawBundleSha(env, ticket.bundle_sha256);
  if (existing === null) {
    await insertTicketedSubmission(env, ticket);
  }
  return jsonResponse(201, ticket);
}

export async function handleRequestUploadTarget(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const parsed = UploadTargetRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_upload_target_request", error: "invalid upload target request" });
  }
  const row = await rowBySubmissionId(env, parsed.data.ticket_id);
  if (row === null || row.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    return jsonResponse(404, { code: "unknown_ticket", error: "unknown submission ticket" });
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
    upload_url: target.uploadUrl,
  });
}

export async function handleFinalizeSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const parsed = CompleteRequestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_complete_request", error: "invalid upload completion request" });
  }
  const existing = await rowByRawBundleSha(env, parsed.data.raw_bundle_sha256);
  if (existing !== null && existing.status === "pending_verification") {
    return jsonResponse(200, publicSubmission(existing));
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  if (row.value.raw_bundle_sha256 !== parsed.data.raw_bundle_sha256) {
    return jsonResponse(409, { code: "bundle_sha_mismatch", error: "raw_bundle_sha256 does not match ticket" });
  }
  const bundleRead = await readRawBundle(env, parsed.data.raw_bundle_sha256);
  if (bundleRead.kind !== "ok") {
    return jsonResponse(bundleRead.status, { code: bundleRead.code, error: bundleRead.error });
  }
  const rawBundle = parseJson(bundleRead.text);
  const bundle = rawBundle === null ? null : ResultBundleSchema.safeParse(rawBundle);
  if (bundle === null || !bundle.success) {
    return jsonResponse(400, { code: "invalid_result_bundle", error: "uploaded bundle does not match result_bundle_v1" });
  }
  await markPendingVerification(env, row.value.submission_id, bundle.data, parsed.data.size_bytes ?? bundleRead.text.length);
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, publicSubmission(updated ?? row.value));
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
  await applyStatusUpdate(env, row.value.submission_id, parsed.data);
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, publicSubmission(updated ?? row.value));
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

function ticketEnvelope(request: TicketRequest): SubmissionEnvelope {
  const ticketId = `ticket_${crypto.randomUUID().replaceAll("-", "")}`;
  const envelope = {
    accepted_suite_terms: true,
    allowed_schema: RESULT_BUNDLE_SCHEMA_VERSION,
    bundle_sha256: request.bundle_sha256,
    expected_suite_manifest_sha256: request.expected_suite_manifest_sha256 ?? DEFAULT_SUITE_MANIFEST_SHA256,
    expected_suite_release_id: request.expected_suite_release_id ?? DEFAULT_SUITE_RELEASE_ID,
    expiry: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    max_upload_bytes: request.max_upload_bytes ?? DEFAULT_MAX_UPLOAD_BYTES,
    one_use: true,
    origin: "project_anchor",
    schema_version: SUBMISSION_ENVELOPE_SCHEMA_VERSION,
    submitter_id: request.submitter_id ?? `public_key:${request.public_key ?? ""}`,
    ticket_id: ticketId,
  } satisfies SubmissionEnvelope;
  if (request.declared_model_slug === undefined) {
    return envelope;
  }
  return { ...envelope, declared_model_slug: request.declared_model_slug };
}

type RouteRowResult =
  | { readonly kind: "ok"; readonly value: Awaited<ReturnType<typeof rowBySubmissionId>> extends infer Row ? Exclude<Row, null> : never }
  | { readonly kind: "error"; readonly response: Response };

async function routeRow(env: SubmissionApiEnv, params: RouteParams): Promise<RouteRowResult> {
  const submissionId = params.submissionId;
  if (submissionId === undefined || submissionId.length === 0) {
    return { kind: "error", response: jsonResponse(400, { code: "missing_submission_id", error: "submission id route param missing" }) };
  }
  const row = await rowBySubmissionId(env, submissionId);
  if (row === null) {
    return { kind: "error", response: jsonResponse(404, { code: "unknown_submission", error: "unknown submission" }) };
  }
  return { kind: "ok", value: row };
}

function adminBlocked(request: Request, env: SubmissionApiEnv): Response | null {
  if (env.ADMIN_API_SECRET === undefined || env.ADMIN_API_SECRET.length === 0) {
    return jsonResponse(503, { code: "admin_api_disabled", error: "submission ticket issuance is disabled" });
  }
  if (request.headers.get("x-localbench-admin-secret") !== env.ADMIN_API_SECRET) {
    return jsonResponse(401, { code: "unauthorized", error: "unauthorized" });
  }
  return null;
}

function parseJson(text: string): unknown | null {
  try {
    const value: unknown = JSON.parse(text);
    return value;
  } catch (error) {
    if (error instanceof SyntaxError) {
      return null;
    }
    throw error;
  }
}

function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, {
    headers: { "cache-control": "no-store" },
    status,
  });
}

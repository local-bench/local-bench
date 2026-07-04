import {
  DEFAULT_SUITE_MANIFEST_SHA256,
  DEFAULT_SUITE_RELEASE_ID,
  MAX_UPLOAD_BYTES,
  RESULT_BUNDLE_SCHEMA_VERSION,
  SUBMISSION_ENVELOPE_SCHEMA_VERSION,
  TicketRequestSchema,
  type SubmissionApiEnv,
  type SubmissionEnvelope,
  type TicketRequest,
} from "./submission-contracts";
import { hasValidAdminSecret, jsonResponse } from "./submission-api-support";
import { clientIp, isRecord, isSyntaxError, reject, type SubmissionOrigin } from "./submission-api-common";
import { verifyTicketPop } from "./submission-pop";
import { rateLimited } from "./submission-rate-limit";
import {
  countPendingVerificationForSubmitter,
  insertTicketedSubmission,
  rotateTicketedSubmission,
  rowByRawBundleSha,
} from "./submission-store";
import { suiteByReleasePair } from "./suite-catalog";

const TICKET_TTL_MILLISECONDS = 60 * 60 * 1000;
const TICKETS_PER_PUBLIC_KEY_PER_DAY = 10;
const TICKETS_PER_IP_PER_HOUR = 30;
const PENDING_VERIFICATION_PER_PUBLIC_KEY = 2;

export async function handleIssueSubmissionTicket(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const origin = hasValidAdminSecret(request, env) ? "project_anchor" : "community";
  if (turnstileEnabled(env)) {
    return reject(503, "turnstile_not_configured", origin, "POST /api/submissions/tickets", {
      code: "turnstile_not_configured",
      error: "turnstile enforcement is not configured",
    });
  }
  let requestBody: unknown;
  try {
    requestBody = await request.json();
  } catch (error) {
    if (isSyntaxError(error)) {
      return invalidTicket(origin);
    }
    throw error;
  }
  if (!isRecord(requestBody) || "origin" in requestBody) {
    return invalidTicket(origin);
  }
  const parsed = TicketRequestSchema.safeParse(requestBody);
  if (!parsed.success) {
    return invalidTicket(origin);
  }
  const communityRejection = await communityTicketRejection(request, env, parsed.data, origin);
  if (communityRejection !== null) {
    return communityRejection;
  }
  const adminRejection = adminTicketRejection(parsed.data, origin);
  if (adminRejection !== null) {
    return adminRejection;
  }
  const ticket = ticketEnvelope(parsed.data, origin);
  const existing = await rowByRawBundleSha(env, ticket.bundle_sha256);
  if (existing === null) {
    await insertTicketedSubmission(env, ticket);
    return jsonResponse(201, ticket);
  }
  if (existing.status === "ticketed" && existing.uploaded_at === null && existing.submitter_id === ticket.submitter_id) {
    await rotateTicketedSubmission(env, existing.submission_id, ticket);
    return jsonResponse(200, ticket);
  }
  return reject(409, "bundle_already_submitted", origin, "POST /api/submissions/tickets", {
    code: "bundle_already_submitted",
    status: existing.status,
    submission_id: existing.submission_id,
  }, ticket.bundle_sha256, ticket.submitter_id);
}

async function communityTicketRejection(
  request: Request,
  env: SubmissionApiEnv,
  body: TicketRequest,
  origin: SubmissionOrigin,
): Promise<Response | null> {
  if (origin !== "community") {
    return null;
  }
  const publicKey = body.public_key;
  const suiteReleaseId = body.expected_suite_release_id;
  const suiteManifestSha256 = body.expected_suite_manifest_sha256;
  if (
    publicKey === undefined ||
    body.submitter_id !== undefined ||
    body.max_upload_bytes !== undefined ||
    suiteReleaseId === undefined ||
    suiteReleaseId === null ||
    suiteManifestSha256 === undefined ||
    suiteManifestSha256 === null
  ) {
    const submitterId = publicKey === undefined ? undefined : `public_key:${publicKey}`;
    return invalidTicket(origin, body.bundle_sha256, submitterId);
  }
  if (suiteByReleasePair(suiteReleaseId, suiteManifestSha256) === null) {
    return reject(400, "unknown_suite_release", origin, "POST /api/submissions/tickets", {
      code: "unknown_suite_release",
      error: "unknown suite release",
    }, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const popResult = await verifyTicketPop(
    publicKey,
    body.bundle_sha256,
    suiteReleaseId,
    suiteManifestSha256,
    body.pop,
  );
  if (popResult !== "ok") {
    const code = popResult === "stale" ? "pop_stale" : "pop_invalid";
    return reject(400, code, origin, "POST /api/submissions/tickets", {
      code,
      error: "invalid proof of possession",
    }, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const ipLimit = await rateLimited(env, `tickets:ip:${clientIp(request)}`, TICKETS_PER_IP_PER_HOUR, 60 * 60);
  if (ipLimit.limited) {
    return rateLimitResponse(ipLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const publicKeyLimit = await rateLimited(env, `tickets:pubkey:${publicKey}`, TICKETS_PER_PUBLIC_KEY_PER_DAY, 24 * 60 * 60);
  if (publicKeyLimit.limited) {
    return rateLimitResponse(publicKeyLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  if (await countPendingVerificationForSubmitter(env, `public_key:${publicKey}`) >= PENDING_VERIFICATION_PER_PUBLIC_KEY) {
    return rateLimitResponse(60, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  return null;
}

function adminTicketRejection(body: TicketRequest, origin: SubmissionOrigin): Response | null {
  if (origin !== "project_anchor") {
    return null;
  }
  if (body.submitter_id === undefined && body.public_key === undefined) {
    return invalidTicket(origin, body.bundle_sha256);
  }
  return null;
}

function ticketEnvelope(request: TicketRequest, origin: SubmissionOrigin): SubmissionEnvelope {
  const ticketId = `ticket_${crypto.randomUUID().replaceAll("-", "")}`;
  const expiresAt = new Date(Date.now() + TICKET_TTL_MILLISECONDS).toISOString();
  const envelope = {
    accepted_suite_terms: true,
    allowed_schema: RESULT_BUNDLE_SCHEMA_VERSION,
    bundle_sha256: request.bundle_sha256,
    expected_suite_manifest_sha256: request.expected_suite_manifest_sha256 === undefined
      ? DEFAULT_SUITE_MANIFEST_SHA256
      : request.expected_suite_manifest_sha256,
    expected_suite_release_id: request.expected_suite_release_id === undefined
      ? DEFAULT_SUITE_RELEASE_ID
      : request.expected_suite_release_id,
    expires_at: expiresAt,
    expiry: expiresAt,
    max_upload_bytes: request.max_upload_bytes ?? MAX_UPLOAD_BYTES,
    one_use: true,
    origin,
    schema_version: SUBMISSION_ENVELOPE_SCHEMA_VERSION,
    submitter_id: request.submitter_id ?? `public_key:${request.public_key ?? ""}`,
    ticket_id: ticketId,
  } satisfies SubmissionEnvelope;
  if (request.declared_model_slug === undefined) {
    return envelope;
  }
  return { ...envelope, declared_model_slug: request.declared_model_slug };
}

function invalidTicket(origin: SubmissionOrigin, bundleSha256?: string, submitterId?: string): Response {
  return reject(400, "invalid_ticket_request", origin, "POST /api/submissions/tickets", {
    code: "invalid_ticket_request",
    error: "invalid submission ticket request",
  }, bundleSha256, submitterId);
}

function rateLimitResponse(
  retryAfterSeconds: number,
  origin: SubmissionOrigin,
  bundleSha256: string,
  submitterId: string,
): Response {
  return reject(429, "rate_limited", origin, "POST /api/submissions/tickets", {
    code: "rate_limited",
    retry_after_seconds: retryAfterSeconds,
  }, bundleSha256, submitterId);
}

function turnstileEnabled(env: SubmissionApiEnv): boolean {
  return (env.TURNSTILE_ENABLED ?? "").toLowerCase() === "true";
}

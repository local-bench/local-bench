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
import { accountAttributionForPublicKey, githubAttributionAvailable } from "./github-oauth-store";
import {
  countPendingVerificationForSubmitter,
  insertTicketedSubmission,
  rotateTicketedSubmission,
  rowByRawBundleSha,
} from "./submission-store";
import { suiteByReleasePair } from "./suite-catalog";

const TICKET_TTL_MILLISECONDS = 60 * 60 * 1000;
// Per-person caps sized for real submitters (a quant ladder is several bundles in one sitting);
// the IP/prefix/global caps below stay conservative — they are the flood + R2-storage guards.
// Raised 10→20 / 2→5 on 2026-07-07 (launch-week review; infra cost is negligible, see D1/R2 math
// in the session notes — the binding budget is R2 storage, guarded by TICKETS_GLOBAL_PER_DAY).
const TICKETS_PER_PUBLIC_KEY_PER_DAY = 20;
const TICKETS_PER_IP_PER_HOUR = 30;
const TICKETS_PER_IP_PREFIX_PER_DAY = 60;
const TICKETS_GLOBAL_PER_DAY = 400;
const PENDING_VERIFICATION_PER_PUBLIC_KEY = 10;

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
  const hasGithubAttribution = await githubAttributionAvailable(env);
  const attribution = parsed.data.public_key === undefined || !hasGithubAttribution
    ? null
    : await accountAttributionForPublicKey(env, parsed.data.public_key);
  const existing = await rowByRawBundleSha(env, ticket.bundle_sha256);
  if (existing === null) {
    await insertTicketedSubmission(env, ticket, attribution, hasGithubAttribution);
    return jsonResponse(201, ticket);
  }
  if (existing.status === "ticketed" && existing.uploaded_at === null && existing.submitter_id === ticket.submitter_id) {
    await rotateTicketedSubmission(env, existing.submission_id, ticket, attribution, hasGithubAttribution);
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
  const requestIp = clientIp(request);
  const ipLimit = await rateLimited(env, `tickets:ip:${requestIp}`, TICKETS_PER_IP_PER_HOUR, 60 * 60);
  if (ipLimit.limited) {
    return rateLimitResponse(ipLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const prefixLimit = await rateLimited(env, `tickets:ipprefix:${ipPrefix(requestIp)}`, TICKETS_PER_IP_PREFIX_PER_DAY, 24 * 60 * 60);
  if (prefixLimit.limited) {
    return rateLimitResponse(prefixLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const globalLimit = await rateLimited(env, "tickets:global:day", TICKETS_GLOBAL_PER_DAY, 24 * 60 * 60);
  if (globalLimit.limited) {
    return rateLimitResponse(globalLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  const publicKeyLimit = await rateLimited(env, `tickets:pubkey:${publicKey}`, TICKETS_PER_PUBLIC_KEY_PER_DAY, 24 * 60 * 60);
  if (publicKeyLimit.limited) {
    return rateLimitResponse(publicKeyLimit.retryAfterSeconds, origin, body.bundle_sha256, `public_key:${publicKey}`);
  }
  if (await countPendingVerificationForSubmitter(env, `public_key:${publicKey}`) >= PENDING_VERIFICATION_PER_PUBLIC_KEY) {
    // Deliberately NOT the rate_limited shape: this cap clears when the maintainer decides a
    // pending submission, not with time, so a retry_after_seconds hint would be misleading.
    return reject(429, "pending_review_limit", origin, "POST /api/submissions/tickets", {
      code: "pending_review_limit",
      error:
        `you have ${PENDING_VERIFICATION_PER_PUBLIC_KEY} submissions awaiting maintainer review; ` +
        "this clears when one is reviewed, not with time",
      pending_limit: PENDING_VERIFICATION_PER_PUBLIC_KEY,
    }, body.bundle_sha256, `public_key:${publicKey}`);
  }
  if (body.community_model_group_id === undefined) {
    const legacyGroupId = `community-group:${crypto.randomUUID().replaceAll("-", "")}`;
    await env.DB.prepare(
      "insert into community_model_groups (community_model_group_id, declared_model_name) values (?, ?)",
    ).bind(legacyGroupId, body.declared_model_slug ?? "legacy-client submission").run();
    body.community_model_group_id = legacyGroupId;
  }
  const group = await env.DB.prepare(
    "select community_model_group_id from community_model_groups where community_model_group_id = ?",
  ).bind(body.community_model_group_id).first();
  if (group === null) {
    return reject(400, "unknown_community_model_group", origin, "POST /api/submissions/tickets", {
      code: "unknown_community_model_group",
      error: "community model group must be server-issued",
    }, body.bundle_sha256, `public_key:${publicKey}`);
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
  const uploadCapability = `upload_${crypto.randomUUID().replaceAll("-", "")}`;
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
    upload_capability: uploadCapability,
  } satisfies SubmissionEnvelope;
  return {
    ...envelope,
    ...(request.declared_model_slug === undefined ? {} : { declared_model_slug: request.declared_model_slug }),
    ...(request.community_model_group_id === undefined ? {} : { community_model_group_id: request.community_model_group_id }),
    ...(request.submitter_display_name === undefined ? {} : { submitter_display_name: request.submitter_display_name }),
  };
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

function ipPrefix(ip: string): string {
  const ipv4 = ipv4Prefix(ip);
  if (ipv4 !== null) {
    return ipv4;
  }
  const ipv6 = ipv6Prefix(ip);
  return ipv6 ?? ip;
}

function ipv4Prefix(ip: string): string | null {
  const octets = ip.split(".");
  if (octets.length !== 4) {
    return null;
  }
  const parsed = octets.map((octet) => Number.parseInt(octet, 10));
  if (parsed.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) {
    return null;
  }
  return `${parsed[0]}.${parsed[1]}.${parsed[2]}.0/24`;
}

function ipv6Prefix(ip: string): string | null {
  const [address] = ip.toLowerCase().split("%");
  if (address === undefined || !/^[0-9a-f:.]+$/.test(address)) {
    return null;
  }
  const compressed = address.split("::");
  if (compressed.length > 2) {
    return null;
  }
  const head = ipv6Groups(compressed[0] ?? "");
  const tail = compressed.length === 2 ? ipv6Groups(compressed[1] ?? "") : [];
  if (head === null || tail === null) {
    return null;
  }
  const missing = compressed.length === 2 ? 8 - head.length - tail.length : 0;
  if (missing < 0 || (compressed.length === 1 && head.length !== 8)) {
    return null;
  }
  const groups = [...head, ...Array.from({ length: missing }, () => "0"), ...tail];
  if (groups.length !== 8) {
    return null;
  }
  return `${groups.slice(0, 4).map((group) => group.replace(/^0+(?=[0-9a-f])/, "")).join(":")}::/64`;
}

function ipv6Groups(value: string): readonly string[] | null {
  if (value.length === 0) {
    return [];
  }
  const groups = value.split(":");
  if (groups.some((group) => !/^[0-9a-f]{1,4}$/.test(group))) {
    return null;
  }
  return groups;
}

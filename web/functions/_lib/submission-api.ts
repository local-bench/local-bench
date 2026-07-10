import {
  PublishStateDecisionSchema,
  StatusUpdateSchema,
  type RouteParams,
  type SubmissionRow,
  type SubmissionApiEnv,
} from "./submission-contracts";
import { adminBlocked, jsonResponse, logSubmissionError, routeRow } from "./submission-api-support";
import { InvalidTransitionError } from "./submission-state";
import { zt1DecisionForAcceptedSubmission } from "./submission-zt1-decision";
import {
  autoPublishEnabled,
  evaluateFreezeAlarms,
  persistZt1Decision,
  publicSubmissionWithZt1,
  zt1Available,
} from "./submission-zt1-store";
import {
  applyStatusUpdate,
  listSubmissionsByStatus,
  pendingVerificationPosition,
  publicTransitionHistory,
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
  return jsonResponse(200, {
    ...publicSubmission(row.value),
    history: await publicTransitionHistory(env, row.value.submission_id),
  });
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
  return jsonResponse(200, { submissions: rows.map((row) => adminSubmission(row)) });
}

function adminSubmission(row: SubmissionRow): Record<string, string | number | null> {
  return {
    ...publicSubmission(row),
    created_at: d1TimestampToIso(row.created_at),
    raw_bundle_sha256: row.raw_bundle_sha256,
    submitter_display_name: row.submitter_display_name,
  };
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.slice(0, 10)}T${value.slice(11)}Z`
    : value;
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
  const override = new URL(request.url).searchParams.get("override") === "true";
  const position = await pendingVerificationPosition(env, row.value.submission_id);
  if (!override && (position === null || position.position !== 1 || position.position > 5)) {
    return jsonResponse(409, {
      code: "fifo_policy_violation",
      error: "verification must process the oldest ticket inside the five-item cohort; retry with explicit override authority",
      position: position?.position ?? null,
      cohort_cap: 5,
    });
  }
  try {
    await applyStatusUpdate(env, row.value.submission_id, parsed.data);
    const updated = await rowBySubmissionId(env, row.value.submission_id);
    if (updated !== null && parsed.data.status === "accepted") {
      await applyZt1AcceptedDecision(env, updated);
      const decided = await rowBySubmissionId(env, updated.submission_id);
      return jsonResponse(200, await publicSubmissionWithZt1(env, decided ?? updated));
    }
    return jsonResponse(200, updated === null ? publicSubmission(row.value) : await publicSubmissionWithZt1(env, updated));
  } catch (error) {
    if (error instanceof InvalidTransitionError) {
      return invalidTransition(error);
    }
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

async function applyZt1AcceptedDecision(env: SubmissionApiEnv, row: SubmissionRow): Promise<void> {
  if (!await zt1Available(env)) {
    return;
  }
  await evaluateFreezeAlarms(env);
  if (!await autoPublishEnabled(env)) {
    return;
  }
  const plan = await zt1DecisionForAcceptedSubmission(env, row);
  await persistZt1Decision(env, row.submission_id, plan);
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
  try {
    await updatePublishState(env, row.value.submission_id, parsed.data.publish_state);
  } catch (error) {
    if (error instanceof InvalidTransitionError) {
      return invalidTransition(error);
    }
    throw error;
  }
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, publicSubmission(updated ?? row.value));
}

function invalidTransition(error: InvalidTransitionError): Response {
  return jsonResponse(409, {
    code: error.code,
    error: "invalid submission status transition",
    from: error.from,
    to: error.to,
  });
}

import { ModerationReasonSchema, type RouteParams, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, jsonResponse, routeRow } from "./submission-api-support";
import { InvalidTransitionError } from "./submission-state";
import { publicSubmission, rowBySubmissionId, transitionAcceptedToTerminal } from "./submission-store";
import { rebuildCommunityLiveBoard } from "./community-live-board";

export async function handleSuppressSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  return handleAcceptedTerminal(request, env, params, "suppressed");
}

export async function handleWithdrawSubmission(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  return handleAcceptedTerminal(request, env, params, "withdrawn");
}

async function handleAcceptedTerminal(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
  toStatus: "suppressed" | "withdrawn",
): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const row = await routeRow(env, params);
  if (row.kind !== "ok") {
    return row.response;
  }
  const parsed = ModerationReasonSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_reason", error: "reason must be 1-500 characters" });
  }
  try {
    await transitionAcceptedToTerminal(env, row.value.submission_id, toStatus, parsed.data.reason);
    await rebuildCommunityLiveBoard(env);
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

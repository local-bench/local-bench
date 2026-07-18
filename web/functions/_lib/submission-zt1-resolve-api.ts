import { ModerationReasonSchema, type RouteParams, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, jsonResponse, routeRow } from "./submission-api-support";
import { publicSubmission, rowBySubmissionId, updatePublishState } from "./submission-store";
import { autoPublishEnabled, evaluateFreezeAlarms, resolveEscalatedDecision } from "./submission-zt1-store";
import { rebuildCommunityLiveBoard } from "./community-live-board";

// Maintainer exit path for ZT-1 escalation holds (design s12.4: duplicate and
// impersonation holds are maintainer-resolved). Resolving marks the decision
// publishable, audits the action in the server decision log, and then applies
// the normal auto-publish rules (kill-switch and freeze alarms still apply).
export async function handleZt1Resolve(
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
  if (row.value.status !== "accepted") {
    return jsonResponse(409, { code: "not_accepted", error: "only accepted submissions can be resolved" });
  }
  const parsed = ModerationReasonSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_reason", error: "reason must be 1-500 characters" });
  }
  const resolved = await resolveEscalatedDecision(env, row.value.submission_id, parsed.data.reason);
  if (!resolved) {
    return jsonResponse(409, { code: "not_escalated", error: "submission is not in an escalated state" });
  }
  if (await autoPublishEnabled(env)) {
    const alarms = await evaluateFreezeAlarms(env);
    if (alarms.length === 0 && await autoPublishEnabled(env)) {
      await updatePublishState(env, row.value.submission_id, "published", "publish-then-moderate resolve");
    }
  }
  await rebuildCommunityLiveBoard(env);
  const updated = await rowBySubmissionId(env, row.value.submission_id);
  return jsonResponse(200, publicSubmission(updated ?? row.value));
}

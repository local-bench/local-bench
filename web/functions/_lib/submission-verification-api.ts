import { jsonResponse, logSubmissionError, routeRow, authorizeValidatorRoute } from "./submission-api-support";
import { rebuildCommunityLiveBoard } from "./community-live-board";
import { InvalidTransitionError } from "./submission-state";
import { StatusUpdateSchema, type RouteParams, type StatusUpdate, type SubmissionApiEnv, type SubmissionRow } from "./submission-contracts";
import { persistProjectionAndReference } from "./publication-storage";
import { validateAcceptedProjection } from "./submission-projection-validation";
import { zt1DecisionForAcceptedSubmission, type Zt1DecisionPlan } from "./submission-zt1-decision";
import {
  autoPublishEnabled,
  evaluateFreezeAlarms,
  persistZt1Decision,
  publicSubmissionWithZt1,
  zt1Available,
} from "./submission-zt1-store";
import { pendingVerificationPosition, publicSubmission, rowBySubmissionId, updatePublishState } from "./submission-store";
import {
  applyInitialDecision,
  applyProjectionRefresh,
  refreshWasAlreadyApplied,
  type VerificationMutation,
} from "./submission-verification-store";

type AcceptedUpdate = Extract<StatusUpdate, { readonly status: "accepted" }>;

export async function handleApplyVerificationUpdate(
  request: Request,
  env: SubmissionApiEnv,
  params: RouteParams,
): Promise<Response> {
  const auth = authorizeValidatorRoute(request, env);
  if (auth.kind === "blocked") return auth.response;
  const routed = await routeRow(env, params);
  if (routed.kind !== "ok") return routed.response;
  const parsed = StatusUpdateSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_status_update", error: "invalid verifier status update" });
  }
  const update = parsed.data;
  if (routed.value.raw_bundle_sha256 !== update.raw_bundle_sha256) {
    return jsonResponse(409, { code: "bundle_sha_mismatch", error: "status update does not match submission bundle" });
  }
  if (update.status === "rejected" && routed.value.status === "rejected" && routed.value.status_reason === update.reason_code) {
    return jsonResponse(200, await publicSubmissionWithZt1(env, routed.value));
  }
  const operationConflict = await verificationOperationConflict(request, env, routed.value, update);
  if (operationConflict !== null) return operationConflict;
  try {
    if (update.status === "rejected") {
      await applyInitialDecision(env, {
        actor: auth.actor,
        projectionR2Key: null,
        submissionId: routed.value.submission_id,
        update,
      });
      return updatedResponse(env, routed.value);
    }
    if (await refreshWasAlreadyApplied(env, routed.value, update)) {
      return jsonResponse(200, await publicSubmissionWithZt1(env, routed.value));
    }
    const projection = await validateAcceptedProjection(update, routed.value);
    if (projection.kind === "invalid") return projection.response;
    const preDecisionPlan = update.operation === "initial_decision" ? await decisionPlan(env, routed.value) : null;
    if (preDecisionPlan?.reason === "unsafe_metadata") {
      await applyInitialDecision(env, {
        actor: auth.actor,
        projectionR2Key: null,
        submissionId: routed.value.submission_id,
        update: metadataRejection(update),
      });
      return updatedResponse(env, routed.value);
    }
    await persistProjectionAndReference(env, update.projection_object_sha256, projection.canonicalBytes, async (projectionR2Key) => {
      const acceptedMutation: VerificationMutation = {
        actor: auth.actor,
        projectionR2Key,
        submissionId: routed.value.submission_id,
        update,
      };
      if (update.operation === "projection_refresh") {
        await applyProjectionRefresh(env, acceptedMutation);
      } else {
        await applyInitialDecision(env, acceptedMutation);
      }
    });
    const accepted = await rowBySubmissionId(env, routed.value.submission_id);
    if (accepted === null) return jsonResponse(500, { code: "submission_missing", error: "submission disappeared after verification" });
    await applyAcceptedOutcome(env, accepted, await decisionPlan(env, accepted));
    const finalRow = await rowBySubmissionId(env, accepted.submission_id);
    if (update.operation === "projection_refresh" || finalRow?.publish_state === "published") {
      await rebuildCommunityLiveBoard(env);
    }
    return updatedResponse(env, accepted);
  } catch (error) {
    if (error instanceof InvalidTransitionError) return invalidTransition(error);
    logSubmissionError("submission_verification_update_failed", {
      error,
      leg: "apply_status_update",
      route: "POST /api/admin/submissions/:submissionId/verification",
      submission_id: routed.value.submission_id,
    });
    return jsonResponse(500, { code: "submission_verification_update_failed", error: "submission verification update failed" });
  }
}

async function verificationOperationConflict(
  request: Request,
  env: SubmissionApiEnv,
  row: SubmissionRow,
  update: StatusUpdate,
): Promise<Response | null> {
  if (update.operation === "initial_decision") {
    if (row.status !== "pending_verification") {
      return jsonResponse(409, { code: "verification_operation_conflict", error: "initial_decision requires pending_verification" });
    }
    const override = new URL(request.url).searchParams.get("override") === "true";
    const position = await pendingVerificationPosition(env, row.submission_id);
    if (!override && (position === null || position.position !== 1 || position.position > 5)) {
      return jsonResponse(409, {
        code: "fifo_policy_violation",
        error: "verification must process the oldest ticket inside the five-item cohort; retry with explicit override authority",
        position: position?.position ?? null,
        cohort_cap: 5,
      });
    }
    return null;
  }
  if (row.status !== "accepted") {
    return jsonResponse(409, { code: "verification_operation_conflict", error: "projection_refresh requires accepted" });
  }
  if (await refreshWasAlreadyApplied(env, row, update)) return null;
  if (row.state_revision !== update.expected_state_revision) {
    return jsonResponse(409, { code: "state_revision_mismatch", error: "projection refresh state revision is stale" });
  }
  if (row.projection_object_sha256 !== update.previous_projection_object_sha256) {
    return jsonResponse(409, { code: "previous_projection_mismatch", error: "projection refresh previous digest is stale" });
  }
  if (row.validated_at === null || Date.parse(update.validated_at) <= Date.parse(row.validated_at)) {
    return jsonResponse(409, { code: "validated_at_not_newer", error: "projection refresh validated_at must be strictly newer" });
  }
  return null;
}

async function decisionPlan(env: SubmissionApiEnv, row: SubmissionRow): Promise<Zt1DecisionPlan | null> {
  return await zt1Available(env) ? zt1DecisionForAcceptedSubmission(env, row) : null;
}

async function applyAcceptedOutcome(env: SubmissionApiEnv, row: SubmissionRow, plan: Zt1DecisionPlan | null): Promise<void> {
  if (plan === null) return;
  await persistZt1Decision(env, row.submission_id, plan);
  if (plan.zt1Decision !== "publishable" || !await autoPublishEnabled(env)) return;
  const alarms = await evaluateFreezeAlarms(env);
  if (alarms.length === 0 && await autoPublishEnabled(env)) {
    await updatePublishState(env, row.submission_id, "published", "publish-then-moderate auto-publish");
  }
}

function metadataRejection(update: AcceptedUpdate): StatusUpdate {
  return {
    accepted: false,
    operation: "initial_decision",
    raw_bundle_sha256: update.raw_bundle_sha256,
    reason_code: "metadata_unsafe",
    reason_detail: "automatic metadata safety checks failed",
    status: "rejected",
    validated_at: update.validated_at,
    validator_commit: update.validator_commit,
    validator_version: update.validator_version,
  };
}

async function updatedResponse(env: SubmissionApiEnv, fallback: SubmissionRow): Promise<Response> {
  const updated = await rowBySubmissionId(env, fallback.submission_id);
  return jsonResponse(200, updated === null ? publicSubmission(fallback) : await publicSubmissionWithZt1(env, updated));
}

function invalidTransition(error: InvalidTransitionError): Response {
  return jsonResponse(409, {
    code: error.code,
    error: "invalid submission status transition",
    from: error.from,
    to: error.to,
  });
}

import { rebuildCommunityLiveBoard } from "./community-live-board";
import { adminBlocked, jsonResponse } from "./submission-api-support";
import type { SubmissionApiEnv } from "./submission-contracts";
import { updatePublishState } from "./submission-store";

export async function handleMigratePublishThenModerate(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  const result = await env.DB.prepare(
    `select submission_id from submissions
     where status = 'accepted' and publish_state = 'preview' and zt1_decision = 'publishable'
     order by submission_id asc`,
  ).all();
  const submissionIds = result.results.map((row) => {
    const value = row["submission_id"];
    if (typeof value !== "string") throw new Error("migration submission_id must be a string");
    return value;
  });
  for (const submissionId of submissionIds) {
    await updatePublishState(env, submissionId, "published", "publish-then-moderate migration");
  }
  await rebuildCommunityLiveBoard(env);
  return jsonResponse(200, {
    migrated_count: submissionIds.length,
    submission_ids: submissionIds,
  });
}

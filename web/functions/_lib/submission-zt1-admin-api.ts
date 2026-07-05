import { adminBlocked, jsonResponse } from "./submission-api-support";
import type { SubmissionApiEnv } from "./submission-contracts";
import { digest, publishBatch, zt1Available, zt1UnavailableResponse } from "./submission-zt1-store";

export async function handlePublishBatch(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  if (!await zt1Available(env)) {
    return zt1UnavailableResponse();
  }
  return jsonResponse(200, await publishBatch(env));
}

export async function handleDigest(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  if (!await zt1Available(env)) {
    return zt1UnavailableResponse();
  }
  return jsonResponse(200, await digest(env));
}

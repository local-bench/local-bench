import type { SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";

export function oauthDisabledResponse(env: SubmissionApiEnv): Response | null {
  return env.GITHUB_OAUTH_ENABLED === "on" ? null : jsonResponse(503, { code: "oauth_disabled" });
}

export function oauthRateLimitResponse(retryAfterSeconds: number): Response {
  return Response.json({ code: "rate_limited", retry_after_seconds: retryAfterSeconds }, {
    headers: { "cache-control": "no-store", "retry-after": String(retryAfterSeconds) },
    status: 429,
  });
}

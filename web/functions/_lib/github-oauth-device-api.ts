import { GithubDevicePollRequestSchema } from "./github-oauth-contracts";
import {
  GithubOAuthUpstreamError,
  fetchGithubUser,
  pollGithubDeviceCode,
  requestGithubDeviceCode,
} from "./github-oauth-client";
import { oauthDisabledResponse, oauthRateLimitResponse } from "./github-oauth-common";
import {
  bindGithubAccount,
  claimGithubDevicePoll,
  deleteGithubDeviceCode,
  githubDeviceCodeByHandle,
  storeGithubDeviceCode,
  updateGithubDeviceInterval,
} from "./github-oauth-store";
import type { SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { clientIp, isSyntaxError } from "./submission-api-common";
import { verifyAccountBindPop } from "./submission-pop";
import { rateLimited } from "./submission-rate-limit";

const DEVICE_START_PER_IP_PER_HOUR = 10;
const DEVICE_POLL_PER_IP_PER_HOUR = 60;

export async function handleGithubDeviceStart(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const disabled = oauthDisabledResponse(env);
  if (disabled !== null) return disabled;
  const limit = await rateLimited(
    env,
    `oauth:device-start:ip:${clientIp(request)}`,
    DEVICE_START_PER_IP_PER_HOUR,
    60 * 60,
  );
  if (limit.limited) return oauthRateLimitResponse(limit.retryAfterSeconds);
  try {
    const github = await requestGithubDeviceCode(env);
    const handle = `dch_${crypto.randomUUID().replaceAll("-", "")}`;
    await storeGithubDeviceCode(env, {
      deviceCode: github.device_code,
      expiresAt: new Date(Date.now() + github.expires_in * 1000).toISOString(),
      handle,
      intervalSeconds: github.interval,
    });
    return jsonResponse(200, {
      device_code_handle: handle,
      expires_in: github.expires_in,
      interval: github.interval,
      user_code: github.user_code,
      verification_uri: github.verification_uri,
    });
  } catch (error) {
    if (error instanceof GithubOAuthUpstreamError) {
      return jsonResponse(error.status, { code: "github_oauth_upstream_error" });
    }
    throw error;
  }
}

export async function handleGithubDevicePoll(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const disabled = oauthDisabledResponse(env);
  if (disabled !== null) return disabled;
  const limit = await rateLimited(
    env,
    `oauth:device-poll:ip:${clientIp(request)}`,
    DEVICE_POLL_PER_IP_PER_HOUR,
    60 * 60,
  );
  if (limit.limited) return oauthRateLimitResponse(limit.retryAfterSeconds);
  const body = await parsePollRequest(request);
  if (body === null) return jsonResponse(400, { code: "invalid_device_poll_request" });
  const stored = await githubDeviceCodeByHandle(env, body.device_code_handle);
  if (stored === null) return jsonResponse(404, { code: "unknown_device_code_handle" });
  if (Date.parse(stored.expiresAt) <= Date.now()) {
    await deleteGithubDeviceCode(env, body.device_code_handle);
    return jsonResponse(410, { code: "device_code_expired" });
  }
  const retryAfterSeconds = pollRetryAfterSeconds(stored.lastPolledAt, stored.intervalSeconds);
  if (retryAfterSeconds !== null) return oauthRateLimitResponse(retryAfterSeconds);
  if (!(await claimGithubDevicePoll(env, body.device_code_handle, stored.lastPolledAt))) {
    return oauthRateLimitResponse(1);
  }
  try {
    const token = await pollGithubDeviceCode(env, stored.deviceCode);
    if (token.kind === "error") {
      return await deviceTokenError(env, body.device_code_handle, stored.intervalSeconds, token.error, token.interval);
    }
    await deleteGithubDeviceCode(env, body.device_code_handle);
    const user = await fetchGithubUser(env, token.accessToken);
    const githubUserId = String(user.id);
    const popResult = await verifyAccountBindPop(body.public_key, githubUserId, body.pop);
    if (popResult !== "ok") {
      return jsonResponse(401, { code: popResult === "stale" ? "pop_stale" : "pop_invalid" });
    }
    const attribution = await bindGithubAccount(env, user, body.public_key, body.pop.signature);
    return jsonResponse(200, {
      account_id: attribution.accountId,
      github_login: attribution.githubLogin,
    });
  } catch (error) {
    if (error instanceof GithubOAuthUpstreamError) {
      return jsonResponse(error.status, { code: "github_oauth_upstream_error" });
    }
    throw error;
  }
}

async function parsePollRequest(request: Request) {
  try {
    const parsed = GithubDevicePollRequestSchema.safeParse(await request.json());
    return parsed.success ? parsed.data : null;
  } catch (error) {
    if (isSyntaxError(error)) return null;
    throw error;
  }
}

async function deviceTokenError(
  env: SubmissionApiEnv,
  handle: string,
  currentInterval: number,
  error: string,
  githubInterval?: number,
): Promise<Response> {
  if (error === "authorization_pending") return jsonResponse(202, { code: "authorization_pending", interval: currentInterval });
  if (error === "slow_down") {
    const interval = Math.min(githubInterval ?? currentInterval + 5, 60);
    await updateGithubDeviceInterval(env, handle, interval);
    return jsonResponse(429, { code: "slow_down", interval });
  }
  await deleteGithubDeviceCode(env, handle);
  if (error === "expired_token") return jsonResponse(410, { code: "device_code_expired" });
  if (error === "access_denied") return jsonResponse(403, { code: "access_denied" });
  return jsonResponse(502, { code: "github_oauth_error" });
}

function pollRetryAfterSeconds(lastPolledAt: string | null, intervalSeconds: number): number | null {
  if (lastPolledAt === null) return null;
  const nextPollAt = Date.parse(lastPolledAt) + intervalSeconds * 1000;
  if (!Number.isFinite(nextPollAt) || nextPollAt <= Date.now()) return null;
  return Math.max(Math.ceil((nextPollAt - Date.now()) / 1000), 1);
}

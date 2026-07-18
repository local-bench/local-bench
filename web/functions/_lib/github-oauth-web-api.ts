import { GITHUB_OAUTH_CALLBACK_URL, GITHUB_OAUTH_CLIENT_ID } from "./github-oauth-contracts";
import {
  GithubOAuthUpstreamError,
  exchangeGithubAuthorizationCode,
  fetchGithubUser,
} from "./github-oauth-client";
import { oauthDisabledResponse, oauthRateLimitResponse } from "./github-oauth-common";
import { consumeGithubOAuthState, storeGithubOAuthState } from "./github-oauth-store";
import type { SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { clientIp } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";

const OAUTH_STATE_TTL_MILLISECONDS = 10 * 60 * 1000;
const STARTS_PER_IP_PER_HOUR = 30;
const CALLBACKS_PER_IP_PER_HOUR = 30;
const STATE_PATTERN = /^state_[0-9a-f]{32}$/u;

export async function handleGithubStart(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const disabled = oauthDisabledResponse(env);
  if (disabled !== null) return disabled;
  if (githubClientSecret(env) === null) return jsonResponse(503, { code: "oauth_not_configured" });
  const limit = await rateLimited(env, `oauth:start:ip:${clientIp(request)}`, STARTS_PER_IP_PER_HOUR, 60 * 60);
  if (limit.limited) return oauthRateLimitResponse(limit.retryAfterSeconds);
  const stateHandle = `state_${crypto.randomUUID().replaceAll("-", "")}`;
  await storeGithubOAuthState(
    env,
    stateHandle,
    new Date(Date.now() + OAUTH_STATE_TTL_MILLISECONDS).toISOString(),
  );
  const authorizationUrl = new URL("https://github.com/login/oauth/authorize");
  authorizationUrl.searchParams.set("client_id", GITHUB_OAUTH_CLIENT_ID);
  authorizationUrl.searchParams.set("redirect_uri", GITHUB_OAUTH_CALLBACK_URL);
  authorizationUrl.searchParams.set("state", stateHandle);
  return new Response(null, {
    headers: {
      "cache-control": "no-store",
      location: authorizationUrl.toString(),
      "referrer-policy": "no-referrer",
    },
    status: 302,
  });
}

export async function handleGithubCallback(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const disabled = oauthDisabledResponse(env);
  if (disabled !== null) return disabled;
  const limit = await rateLimited(
    env,
    `oauth:callback:ip:${clientIp(request)}`,
    CALLBACKS_PER_IP_PER_HOUR,
    60 * 60,
  );
  if (limit.limited) return oauthRateLimitResponse(limit.retryAfterSeconds);
  const clientSecret = githubClientSecret(env);
  if (clientSecret === null) return jsonResponse(503, { code: "oauth_not_configured" });
  const url = new URL(request.url);
  const codes = url.searchParams.getAll("code");
  const states = url.searchParams.getAll("state");
  const code = codes.length === 1 ? codes[0] : undefined;
  const state = states.length === 1 ? states[0] : undefined;
  if (
    code === undefined || code.length === 0 || code.length > 200 ||
    state === undefined || !STATE_PATTERN.test(state) ||
    !(await consumeGithubOAuthState(env, state))
  ) return jsonResponse(400, { code: "invalid_oauth_state" });
  try {
    const accessToken = await exchangeGithubAuthorizationCode(env, code, clientSecret);
    const user = await fetchGithubUser(env, accessToken);
    return completionPage(user.login);
  } catch (error) {
    if (error instanceof GithubOAuthUpstreamError) {
      return jsonResponse(error.status, { code: "github_oauth_upstream_error" });
    }
    throw error;
  }
}

function githubClientSecret(env: SubmissionApiEnv): string | null {
  const secret = (env.GITHUB_OAUTH_CLIENT_SECRET ?? "").trim();
  return secret.length === 0 ? null : secret;
}

function completionPage(githubLogin: string): Response {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GitHub authorization complete</title></head><body><main><h1>GitHub authorization complete</h1><p>@${githubLogin} was verified for this browser authorization.</p><p>Return to your terminal and run <code>localbench login</code> to finish binding your submitter key.</p></main></body></html>`;
  return new Response(body, {
    headers: {
      "cache-control": "no-store",
      "content-security-policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
      "content-type": "text/html; charset=utf-8",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
    },
    status: 200,
  });
}

import {
  GITHUB_OAUTH_CALLBACK_URL,
  GITHUB_OAUTH_CLIENT_ID,
  GithubDeviceCodeResponseSchema,
  GithubTokenResponseSchema,
  GithubUserSchema,
  type GithubUser,
} from "./github-oauth-contracts";
import type { SubmissionApiEnv } from "./submission-contracts";

const GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code";
const GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token";
const GITHUB_USER_URL = "https://api.github.com/user";

export class GithubOAuthUpstreamError extends Error {
  constructor(readonly status: number) {
    super("GitHub OAuth upstream response was invalid");
    this.name = "GithubOAuthUpstreamError";
  }
}

export type GithubTokenResult =
  | { readonly accessToken: string; readonly kind: "token" }
  | { readonly error: string; readonly interval?: number; readonly kind: "error" };

export async function requestGithubDeviceCode(env: SubmissionApiEnv) {
  const value = await postGithubForm(env, GITHUB_DEVICE_CODE_URL, { client_id: GITHUB_OAUTH_CLIENT_ID });
  const parsed = GithubDeviceCodeResponseSchema.safeParse(value);
  if (!parsed.success) throw new GithubOAuthUpstreamError(502);
  return parsed.data;
}

export async function pollGithubDeviceCode(env: SubmissionApiEnv, deviceCode: string): Promise<GithubTokenResult> {
  const value = await postGithubForm(env, GITHUB_ACCESS_TOKEN_URL, {
    client_id: GITHUB_OAUTH_CLIENT_ID,
    device_code: deviceCode,
    grant_type: "urn:ietf:params:oauth:grant-type:device_code",
  });
  const parsed = GithubTokenResponseSchema.safeParse(value);
  if (!parsed.success) throw new GithubOAuthUpstreamError(502);
  if ("access_token" in parsed.data && typeof parsed.data.access_token === "string") {
    return { accessToken: parsed.data.access_token, kind: "token" };
  }
  if (typeof parsed.data.error !== "string") throw new GithubOAuthUpstreamError(502);
  const interval = parsed.data.interval;
  return {
    error: parsed.data.error,
    kind: "error",
    ...(typeof interval === "number" ? { interval } : {}),
  };
}

export async function exchangeGithubAuthorizationCode(
  env: SubmissionApiEnv,
  code: string,
  clientSecret: string,
): Promise<string> {
  const value = await postGithubForm(env, GITHUB_ACCESS_TOKEN_URL, {
    client_id: GITHUB_OAUTH_CLIENT_ID,
    client_secret: clientSecret,
    code,
    redirect_uri: GITHUB_OAUTH_CALLBACK_URL,
  });
  const parsed = GithubTokenResponseSchema.safeParse(value);
  if (!parsed.success || !("access_token" in parsed.data) || typeof parsed.data.access_token !== "string") {
    throw new GithubOAuthUpstreamError(502);
  }
  return parsed.data.access_token;
}

export async function fetchGithubUser(env: SubmissionApiEnv, accessToken: string): Promise<GithubUser> {
  const response = await githubFetch(env)(GITHUB_USER_URL, {
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${accessToken}`,
      "user-agent": "local-bench-oauth/0.4.3",
      "x-github-api-version": "2022-11-28",
    },
    method: "GET",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new GithubOAuthUpstreamError(502);
  const parsed = GithubUserSchema.safeParse(await response.json());
  if (!parsed.success) throw new GithubOAuthUpstreamError(502);
  return parsed.data;
}

async function postGithubForm(
  env: SubmissionApiEnv,
  url: string,
  form: Readonly<Record<string, string>>,
): Promise<unknown> {
  const response = await githubFetch(env)(url, {
    body: new URLSearchParams(form),
    headers: {
      accept: "application/json",
      "content-type": "application/x-www-form-urlencoded",
      "user-agent": "local-bench-oauth/0.4.3",
    },
    method: "POST",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new GithubOAuthUpstreamError(502);
  return await response.json();
}

function githubFetch(env: SubmissionApiEnv) {
  return env.GITHUB_FETCH ?? globalThis.fetch;
}

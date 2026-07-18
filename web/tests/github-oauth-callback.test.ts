import { describe, expect, it } from "vitest";
import { onRequestGet as callback } from "../functions/api/auth/github/callback";
import { onRequestGet as startWeb } from "../functions/api/auth/github/start";
import {
  GITHUB_LOGIN,
  OAUTH_TEST_IP,
  createGithubMock,
  createOAuthEnv,
  oauthGet,
  persistedOAuthStorage,
  seedOAuthRateLimit,
} from "./github-oauth-test-support";

describe("GitHub OAuth web callback", () => {
  it("issues single-use state and renders a sessionless completion page", async () => {
    // Given: OAuth is enabled with an injected GitHub exchange and user endpoint.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);

    // When: the redirect helper issues state and GitHub returns the authorization code once.
    const startResponse = await startWeb({ env, request: oauthGet("/api/auth/github/start") });
    const location = startResponse.headers.get("location");
    if (location === null) throw new Error("OAuth start must provide a redirect location");
    const authorizationUrl = new URL(location);
    const state = authorizationUrl.searchParams.get("state");
    if (state === null) throw new Error("OAuth start must provide state");
    const callbackResponse = await callback({
      env,
      request: oauthGet(`/api/auth/github/callback?code=temporary-code&state=${encodeURIComponent(state)}`),
    });
    const html = await callbackResponse.text();

    // Then: state is consumed, the token is absent everywhere, and no session or cookie is created.
    expect(startResponse.status).toBe(302);
    expect(authorizationUrl.origin).toBe("https://github.com");
    expect(authorizationUrl.pathname).toBe("/login/oauth/authorize");
    expect(authorizationUrl.searchParams.get("client_id")).toBe("Ov23liGbCyw1WtlJ0jmj");
    expect(callbackResponse.status).toBe(200);
    expect(callbackResponse.headers.get("set-cookie")).toBeNull();
    expect(callbackResponse.headers.get("cache-control")).toBe("no-store");
    expect(html).toContain(`@${GITHUB_LOGIN}`);
    expect(html).toContain("localbench login");
    expect(html).not.toContain("gho_");
    expect((await env.DB.prepare("select count(*) as count from github_oauth_states").first())?.["count"]).toBe(0);
    const persisted = await persistedOAuthStorage(env);
    expect(persisted).not.toContain("gho_");
    expect(persisted).not.toContain("ghu_");

    // When: the same state is replayed.
    const replay = await callback({
      env,
      request: oauthGet(`/api/auth/github/callback?code=second-code&state=${encodeURIComponent(state)}`),
    });

    // Then: replay is rejected before another GitHub exchange.
    expect(replay.status).toBe(400);
    expect(await replay.json()).toEqual({ code: "invalid_oauth_state" });
    expect(mock.calls).toHaveLength(2);
  });

  it("rejects missing and expired callback state before token exchange", async () => {
    // Given: one request has no state and one names an expired state row.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    const expiredState = `state_${"a".repeat(32)}`;
    await env.DB.prepare("insert into github_oauth_states (state_handle, expires_at) values (?, ?)")
      .bind(expiredState, "2020-01-01T00:00:00.000Z")
      .run();

    // When: both callbacks are attempted.
    const missing = await callback({ env, request: oauthGet("/api/auth/github/callback?code=temporary-code") });
    const expired = await callback({
      env,
      request: oauthGet(`/api/auth/github/callback?code=temporary-code&state=${expiredState}`),
    });

    // Then: both receive the same non-oracular validation response without contacting GitHub.
    expect(missing.status).toBe(400);
    expect(expired.status).toBe(400);
    expect(await missing.json()).toEqual({ code: "invalid_oauth_state" });
    expect(await expired.json()).toEqual({ code: "invalid_oauth_state" });
    expect(mock.calls).toHaveLength(0);
  });

  it("enforces the callback hourly IP budget before state validation", async () => {
    // Given: the caller has exhausted thirty callback attempts in the current hour.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    await seedOAuthRateLimit(env, `oauth:callback:ip:${OAUTH_TEST_IP}`, 30);

    // When: one more callback request arrives.
    const response = await callback({ env, request: oauthGet("/api/auth/github/callback") });

    // Then: it is rate-limited without touching GitHub.
    expect(response.status).toBe(429);
    expect(await response.json()).toMatchObject({ code: "rate_limited" });
    expect(mock.calls).toHaveLength(0);
  });
});

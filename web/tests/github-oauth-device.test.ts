import { z } from "zod";
import { describe, expect, it } from "vitest";
import { onRequestGet as callback } from "../functions/api/auth/github/callback";
import { onRequestPost as pollDevice } from "../functions/api/auth/github/device/poll";
import { onRequestPost as startDevice } from "../functions/api/auth/github/device/start";
import { onRequestGet as startWeb } from "../functions/api/auth/github/start";
import { testKeyPair } from "./submission-contract-v2-support";
import {
  GITHUB_LOGIN,
  OAUTH_TEST_IP,
  accountBindBody,
  createGithubMock,
  createOAuthEnv,
  oauthGet,
  oauthPost,
  persistedOAuthStorage,
  seedOAuthRateLimit,
} from "./github-oauth-test-support";

const DeviceStartSchema = z.object({
  device_code_handle: z.string().regex(/^dch_[0-9a-f]{32}$/u),
  expires_in: z.number().int().positive(),
  interval: z.number().int().positive(),
  user_code: z.string(),
  verification_uri: z.string().url(),
}).strict();

describe("GitHub OAuth device flow", () => {
  it("returns the disabled shape from every OAuth endpoint when the flag is off", async () => {
    // Given: GitHub OAuth is not enabled and outbound GitHub access must not occur.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock, "off");

    // When: each new endpoint is called.
    const responses = await Promise.all([
      startDevice({ env, request: oauthPost("/api/auth/github/device/start") }),
      pollDevice({ env, request: oauthPost("/api/auth/github/device/poll", {}) }),
      startWeb({ env, request: oauthGet("/api/auth/github/start") }),
      callback({ env, request: oauthGet("/api/auth/github/callback") }),
    ]);

    // Then: every route is inert behind the same 503 feature-flag response.
    expect(responses.map((response) => response.status)).toEqual([503, 503, 503, 503]);
    for (const response of responses) {
      expect(await response.json()).toEqual({ code: "oauth_disabled" });
    }
    expect(mock.calls).toHaveLength(0);
  });

  it("keeps device codes opaque, binds two keys idempotently, and persists no access token", async () => {
    // Given: GitHub authorizes the same user in two independent device flows.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    const firstKey = testKeyPair();
    const secondKey = testKeyPair();

    // When: both opaque handles are started and polled with key-bound PoP signatures.
    const firstStartResponse = await startDevice({ env, request: oauthPost("/api/auth/github/device/start") });
    const firstStartText = await firstStartResponse.text();
    const firstStart = DeviceStartSchema.parse(JSON.parse(firstStartText));
    const firstPoll = await pollDevice({
      env,
      request: oauthPost("/api/auth/github/device/poll", accountBindBody(firstStart.device_code_handle, firstKey)),
    });
    const secondStartResponse = await startDevice({ env, request: oauthPost("/api/auth/github/device/start") });
    const secondStartText = await secondStartResponse.text();
    const secondStart = DeviceStartSchema.parse(JSON.parse(secondStartText));
    const secondPoll = await pollDevice({
      env,
      request: oauthPost("/api/auth/github/device/poll", accountBindBody(secondStart.device_code_handle, secondKey)),
    });

    // Then: raw device codes and GitHub tokens never leave or remain, while one account owns both keys.
    expect(firstStartResponse.status).toBe(200);
    expect(secondStartResponse.status).toBe(200);
    expect(firstStart.device_code_handle).not.toBe(secondStart.device_code_handle);
    expect(firstStartText).not.toContain(mock.deviceCodes[0]);
    expect(secondStartText).not.toContain(mock.deviceCodes[1]);
    expect(firstPoll.status).toBe(200);
    expect(secondPoll.status).toBe(200);
    const firstAccount = await firstPoll.json();
    const secondAccount = await secondPoll.json();
    expect(firstAccount).toMatchObject({ github_login: GITHUB_LOGIN });
    expect(firstAccount).toEqual(secondAccount);
    expect(firstAccount).toMatchObject({ account_id: expect.stringMatching(/^acct_[0-9a-f]{32}$/u) });
    expect((await env.DB.prepare("select count(*) as count from accounts").first())?.["count"]).toBe(1);
    expect((await env.DB.prepare("select count(*) as count from account_keys").first())?.["count"]).toBe(2);
    expect((await env.DB.prepare("select count(*) as count from github_oauth_device_codes").first())?.["count"]).toBe(0);
    const persisted = await persistedOAuthStorage(env);
    expect(persisted).not.toContain("gho_");
    expect(persisted).not.toContain("ghu_");
  }, 20_000);

  it("rejects bad key possession and consumes the authorized device handle", async () => {
    // Given: GitHub returns a user but the caller cannot sign with the key being bound.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    const startResponse = await startDevice({ env, request: oauthPost("/api/auth/github/device/start") });
    const started = DeviceStartSchema.parse(await startResponse.json());

    // When: the caller submits a correctly shaped but invalid Ed25519 signature.
    const response = await pollDevice({
      env,
      request: oauthPost("/api/auth/github/device/poll", {
        device_code_handle: started.device_code_handle,
        pop: { signature: "0".repeat(128), timestamp: new Date().toISOString() },
        public_key: testKeyPair().publicKeyHex,
      }),
    });
    const staleStart = DeviceStartSchema.parse(await (
      await startDevice({ env, request: oauthPost("/api/auth/github/device/start") })
    ).json());
    const staleResponse = await pollDevice({
      env,
      request: oauthPost(
        "/api/auth/github/device/poll",
        accountBindBody(staleStart.device_code_handle, testKeyPair(), undefined, "2020-01-01T00:00:00.000Z"),
      ),
    });

    // Then: binding is unauthorized and the single-use handle cannot be replayed.
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ code: "pop_invalid" });
    expect(staleResponse.status).toBe(401);
    expect(await staleResponse.json()).toEqual({ code: "pop_stale" });
    expect((await env.DB.prepare("select count(*) as count from accounts").first())?.["count"]).toBe(0);
    expect((await env.DB.prepare("select count(*) as count from github_oauth_device_codes").first())?.["count"]).toBe(0);
  });

  it("returns 410 for an expired opaque handle before contacting GitHub", async () => {
    // Given: an expired raw device code exists only behind an opaque server handle.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    const handle = `dch_${"a".repeat(32)}`;
    await env.DB.prepare(
      "insert into github_oauth_device_codes (device_code_handle, device_code, expires_at, interval_seconds) values (?, ?, ?, ?)",
    ).bind(handle, "expired-raw-device-code", "2020-01-01T00:00:00.000Z", 5).run();

    // When: the CLI polls the expired handle.
    const response = await pollDevice({
      env,
      request: oauthPost("/api/auth/github/device/poll", accountBindBody(handle, testKeyPair())),
    });

    // Then: the server consumes it and reports expiry without exposing or sending the raw code.
    expect(response.status).toBe(410);
    expect(await response.json()).toEqual({ code: "device_code_expired" });
    expect(mock.calls).toHaveLength(0);
    expect((await env.DB.prepare("select count(*) as count from github_oauth_device_codes").first())?.["count"]).toBe(0);
  });

  it("allows only one in-flight poll to consume an opaque handle", async () => {
    // Given: two callers race the same valid handle and proof of key possession.
    const mock = createGithubMock();
    const env = await createOAuthEnv(mock);
    const startResponse = await startDevice({ env, request: oauthPost("/api/auth/github/device/start") });
    const started = DeviceStartSchema.parse(await startResponse.json());
    const body = accountBindBody(started.device_code_handle, testKeyPair());

    // When: both requests attempt the first GitHub poll concurrently.
    const responses = await Promise.all([
      pollDevice({ env, request: oauthPost("/api/auth/github/device/poll", body) }),
      pollDevice({ env, request: oauthPost("/api/auth/github/device/poll", body) }),
    ]);

    // Then: only one request reaches the token endpoint and binds the account.
    expect(responses.map((response) => response.status).sort()).toEqual([200, 429]);
    expect(mock.tokens).toHaveLength(1);
    expect((await env.DB.prepare("select count(*) as count from account_keys").first())?.["count"]).toBe(1);
  });

  it("enforces the device start and poll hourly IP budgets", async () => {
    // Given: separate callers have exhausted the start and poll rate buckets.
    const startMock = createGithubMock();
    const startEnv = await createOAuthEnv(startMock);
    await seedOAuthRateLimit(startEnv, `oauth:device-start:ip:${OAUTH_TEST_IP}`, 10);
    const pollMock = createGithubMock();
    const pollEnv = await createOAuthEnv(pollMock);
    await seedOAuthRateLimit(pollEnv, `oauth:device-poll:ip:${OAUTH_TEST_IP}`, 60);

    // When: each caller makes one more request.
    const startResponse = await startDevice({ env: startEnv, request: oauthPost("/api/auth/github/device/start") });
    const pollResponse = await pollDevice({ env: pollEnv, request: oauthPost("/api/auth/github/device/poll", {}) });

    // Then: both are rejected before parsing or contacting GitHub.
    expect(startResponse.status).toBe(429);
    expect(pollResponse.status).toBe(429);
    expect(startMock.calls).toHaveLength(0);
    expect(pollMock.calls).toHaveLength(0);
  });
});

import { z } from "zod";
import type { SubmissionApiEnv } from "../functions/_lib/submission-contracts";
import { createEnv } from "./submission-test-support";
import type { TestKeyPair } from "./submission-contract-v2-support";

export const GITHUB_USER_ID = "1234567";
export const GITHUB_LOGIN = "octocat";
export const OAUTH_TEST_IP = "198.51.100.42";

export type GithubFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type OAuthTestEnv = SubmissionApiEnv & {
  readonly GITHUB_FETCH: GithubFetch;
  readonly GITHUB_OAUTH_CLIENT_SECRET: string;
  readonly GITHUB_OAUTH_ENABLED: string;
};

export type GithubMock = {
  readonly calls: readonly GithubCall[];
  readonly deviceCodes: readonly string[];
  readonly fetch: GithubFetch;
  readonly tokens: readonly string[];
};

type GithubCall = {
  readonly authorization: string | null;
  readonly body: string;
  readonly url: string;
};

export async function createOAuthEnv(mock: GithubMock, enabled = "on"): Promise<OAuthTestEnv> {
  const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
  return {
    ...env,
    GITHUB_FETCH: mock.fetch,
    GITHUB_OAUTH_CLIENT_SECRET: "test-github-client-secret",
    GITHUB_OAUTH_ENABLED: enabled,
  };
}

export function createGithubMock(): GithubMock {
  const calls: GithubCall[] = [];
  const deviceCodes: string[] = [];
  const tokens: string[] = [];
  const githubFetch: GithubFetch = async (input, init) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const body = await request.clone().text();
    calls.push({ authorization: request.headers.get("authorization"), body, url: request.url });
    if (request.url === "https://github.com/login/device/code") {
      const sequence = deviceCodes.length + 1;
      const deviceCode = `raw-device-code-${sequence}`;
      deviceCodes.push(deviceCode);
      return Response.json({
        device_code: deviceCode,
        expires_in: 900,
        interval: 5,
        user_code: `CODE-000${sequence}`,
        verification_uri: "https://github.com/login/device",
      });
    }
    if (request.url === "https://github.com/login/oauth/access_token") {
      const sequence = tokens.length + 1;
      const token = `gho_test_token_${sequence}`;
      tokens.push(token);
      return Response.json({ access_token: token, scope: "", token_type: "bearer" });
    }
    if (request.url === "https://api.github.com/user") {
      return Response.json({ id: Number(GITHUB_USER_ID), login: GITHUB_LOGIN });
    }
    return Response.json({ message: "unexpected GitHub URL" }, { status: 404 });
  };
  return { calls, deviceCodes, fetch: githubFetch, tokens };
}

export function accountBindBody(
  handle: string,
  key: TestKeyPair,
  githubUserId = GITHUB_USER_ID,
  timestamp = new Date().toISOString(),
): Record<string, unknown> {
  return {
    device_code_handle: handle,
    pop: {
      signature: key.signMessage(`localbench.account_bind.v1\n${githubUserId}\n${timestamp}`),
      timestamp,
    },
    public_key: key.publicKeyHex,
  };
}

export function oauthGet(path: string, ip = OAUTH_TEST_IP): Request {
  return new Request(`https://local-bench.ai${path}`, {
    headers: { "CF-Connecting-IP": ip },
    method: "GET",
  });
}

export function oauthPost(path: string, body?: unknown, ip = OAUTH_TEST_IP): Request {
  return new Request(`https://local-bench.ai${path}`, {
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    headers: { "CF-Connecting-IP": ip, "content-type": "application/json" },
    method: "POST",
  });
}

export async function seedOAuthRateLimit(
  env: SubmissionApiEnv,
  bucketKey: string,
  count: number,
): Promise<void> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % 3600);
  await env.DB.prepare("insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)")
    .bind(bucketKey, new Date(windowStartSeconds * 1000).toISOString(), count)
    .run();
}

export async function persistedOAuthStorage(env: SubmissionApiEnv): Promise<string> {
  const tableRows = await env.DB.prepare(
    "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' and name not glob '_cf_*' order by name",
  ).all();
  const database: Record<string, readonly Record<string, unknown>[]> = {};
  for (const row of tableRows.results) {
    const name = row["name"];
    if (typeof name !== "string" || !/^[a-z0-9_]+$/u.test(name)) {
      throw new Error(`unexpected D1 table name: ${String(name)}`);
    }
    database[name] = (await env.DB.prepare(`select * from ${name}`).all()).results;
  }
  const listMethod = Reflect.get(env.SUBMISSIONS, "list");
  if (typeof listMethod !== "function") throw new Error("R2 list binding is required for persistence audit");
  const listing = z.object({ objects: z.array(z.object({ key: z.string() }).passthrough()) }).passthrough()
    .parse(await Reflect.apply(listMethod, env.SUBMISSIONS, []));
  const objects: Record<string, string> = {};
  for (const object of listing.objects) {
    const stored = await env.SUBMISSIONS.get(object.key);
    objects[object.key] = stored === null ? "" : await new Response(stored.body).text();
  }
  return JSON.stringify({ database, objects });
}

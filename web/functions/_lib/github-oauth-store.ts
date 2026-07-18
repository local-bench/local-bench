import type { GithubUser } from "./github-oauth-contracts";
import type { SubmissionApiEnv } from "./submission-contracts";

export type GithubDeviceCode = {
  readonly deviceCode: string;
  readonly expiresAt: string;
  readonly intervalSeconds: number;
  readonly lastPolledAt: string | null;
};

export type AccountAttribution = {
  readonly accountId: string;
  readonly githubLogin: string;
};

export class GithubOAuthStoreError extends Error {
  constructor() {
    super("GitHub OAuth storage invariant failed");
    this.name = "GithubOAuthStoreError";
  }
}

// Per-isolate memo (keyed by the D1 binding so tests with distinct envs never share
// state): the accounts schema only ever gets ADDED within an isolate's life, so a
// confirmed-ready result is safe to cache; a not-yet-ready result is never cached so
// a rolling migration is picked up. Removes two sqlite_master/pragma probes per
// ticket/board/lifecycle request once the schema is present.
const attributionSchemaReady = new WeakSet<object>();

export async function githubAttributionAvailable(env: SubmissionApiEnv): Promise<boolean> {
  if (attributionSchemaReady.has(env.DB)) return true;
  const tables = await env.DB.prepare(
    "select count(*) as count from sqlite_master where type = 'table' and name in ('accounts', 'account_keys')",
  ).first();
  const column = await env.DB.prepare(
    "select count(*) as count from pragma_table_info('submissions') where name = 'github_login'",
  ).first();
  const ready = tables?.["count"] === 2 && column?.["count"] === 1;
  if (ready) attributionSchemaReady.add(env.DB);
  return ready;
}

export async function storeGithubDeviceCode(
  env: SubmissionApiEnv,
  values: {
    readonly deviceCode: string;
    readonly expiresAt: string;
    readonly handle: string;
    readonly intervalSeconds: number;
  },
): Promise<void> {
  await env.DB.prepare(
    "insert into github_oauth_device_codes (device_code_handle, device_code, expires_at, interval_seconds) values (?, ?, ?, ?)",
  ).bind(values.handle, values.deviceCode, values.expiresAt, values.intervalSeconds).run();
}

export async function githubDeviceCodeByHandle(env: SubmissionApiEnv, handle: string): Promise<GithubDeviceCode | null> {
  const row = await env.DB.prepare(
    "select device_code, expires_at, interval_seconds, last_polled_at from github_oauth_device_codes where device_code_handle = ?",
  ).bind(handle).first();
  if (row === null) return null;
  const deviceCode = row["device_code"];
  const expiresAt = row["expires_at"];
  const intervalSeconds = row["interval_seconds"];
  const lastPolledAt = row["last_polled_at"];
  if (
    typeof deviceCode !== "string" || typeof expiresAt !== "string" || typeof intervalSeconds !== "number" ||
    (lastPolledAt !== null && typeof lastPolledAt !== "string")
  ) throw new GithubOAuthStoreError();
  return { deviceCode, expiresAt, intervalSeconds, lastPolledAt };
}

export async function claimGithubDevicePoll(
  env: SubmissionApiEnv,
  handle: string,
  expectedLastPolledAt: string | null,
): Promise<boolean> {
  const result = await env.DB.prepare(
    "update github_oauth_device_codes set last_polled_at = ? where device_code_handle = ? and last_polled_at is ?",
  )
    .bind(new Date().toISOString(), handle, expectedLastPolledAt)
    .run();
  return result.meta?.changes === 1;
}

export async function updateGithubDeviceInterval(env: SubmissionApiEnv, handle: string, interval: number): Promise<void> {
  await env.DB.prepare("update github_oauth_device_codes set interval_seconds = ? where device_code_handle = ?")
    .bind(interval, handle)
    .run();
}

export async function deleteGithubDeviceCode(env: SubmissionApiEnv, handle: string): Promise<void> {
  await env.DB.prepare("delete from github_oauth_device_codes where device_code_handle = ?").bind(handle).run();
}

export async function bindGithubAccount(
  env: SubmissionApiEnv,
  user: GithubUser,
  publicKeyHex: string,
  bindingSignature: string,
): Promise<AccountAttribution> {
  const candidateAccountId = `acct_${crypto.randomUUID().replaceAll("-", "")}`;
  const githubUserId = String(user.id);
  // Ordinary binding must NEVER clear revoked_at: a revoked account (e.g. after a
  // key compromise) stays dark until an explicit admin recovery, so binding a new
  // key cannot silently reactivate an account whose historical keys are still
  // present in account_keys. Only the login label is refreshed on conflict.
  await env.DB.prepare(
    `insert into accounts (account_id, github_user_id, github_login) values (?, ?, ?)
     on conflict(github_user_id) do update set github_login = excluded.github_login`,
  ).bind(candidateAccountId, githubUserId, user.login).run();
  const account = await env.DB.prepare("select account_id from accounts where github_user_id = ?")
    .bind(githubUserId)
    .first();
  const accountId = account?.["account_id"];
  if (typeof accountId !== "string") throw new GithubOAuthStoreError();
  await env.DB.prepare(
    `insert into account_keys (public_key_hex, account_id, binding_signature) values (?, ?, ?)
     on conflict(public_key_hex) do update set account_id = excluded.account_id, bound_at = datetime('now'), binding_signature = excluded.binding_signature`,
  ).bind(publicKeyHex, accountId, bindingSignature).run();
  return { accountId, githubLogin: user.login };
}

export async function accountAttributionForPublicKey(
  env: SubmissionApiEnv,
  publicKeyHex: string,
): Promise<AccountAttribution | null> {
  if (!(await githubAttributionAvailable(env))) return null;
  const row = await env.DB.prepare(
    `select a.account_id, a.github_login from account_keys k join accounts a on a.account_id = k.account_id
     where k.public_key_hex = ? and a.revoked_at is null`,
  ).bind(publicKeyHex).first();
  if (row === null) return null;
  const accountId = row["account_id"];
  const githubLogin = row["github_login"];
  if (typeof accountId !== "string" || typeof githubLogin !== "string") throw new GithubOAuthStoreError();
  return { accountId, githubLogin };
}

export async function storeGithubOAuthState(
  env: SubmissionApiEnv,
  stateHandle: string,
  expiresAt: string,
): Promise<void> {
  // Opportunistically evict already-expired states so abandoned authorize starts
  // cannot accumulate unbounded (they are otherwise removed only when their exact
  // handle reaches the callback).
  await env.DB.prepare("delete from github_oauth_states where expires_at <= ?")
    .bind(new Date().toISOString())
    .run();
  await env.DB.prepare("insert into github_oauth_states (state_handle, expires_at) values (?, ?)")
    .bind(stateHandle, expiresAt)
    .run();
}

export async function consumeGithubOAuthState(env: SubmissionApiEnv, stateHandle: string): Promise<boolean> {
  const row = await env.DB.prepare("delete from github_oauth_states where state_handle = ? returning expires_at")
    .bind(stateHandle)
    .first();
  const expiresAt = row?.["expires_at"];
  return typeof expiresAt === "string" && Date.parse(expiresAt) > Date.now();
}

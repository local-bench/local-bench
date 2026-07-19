import { REJECTION_REASON_CODES, type SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { clientIp } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";
import { githubAttributionAvailable } from "./github-oauth-store";

const PAGE_SIZE = 50;
const CACHE_SECONDS = 60;
const MISSES_PER_IP_PER_MINUTE = 30;
const rejectionReasons = new Set<string>(REJECTION_REASON_CODES);

type Cursor = {
  readonly createdAt: string;
  readonly submissionId: string;
};

export async function handleSubmissionLifecycleList(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const url = new URL(request.url);
  if ([...url.searchParams.keys()].some((key) => key !== "cursor") || url.searchParams.getAll("cursor").length > 1) {
    return jsonResponse(400, { code: "invalid_cursor", error: "invalid lifecycle cursor" });
  }
  const rawCursor = url.searchParams.get("cursor");
  const cursor = rawCursor === null ? null : decodeCursor(rawCursor);
  if (rawCursor !== null && cursor === null) {
    return jsonResponse(400, { code: "invalid_cursor", error: "invalid lifecycle cursor" });
  }
  const cache = edgeCache();
  const cacheKey = new Request(url);
  const cached = cache === null ? undefined : await cache.match(cacheKey);
  if (cached !== undefined) return cached;
  const limit = await rateLimited(env, `submission-list:ip:${clientIp(request)}`, MISSES_PER_IP_PER_MINUTE, 60);
  if (limit.limited) {
    return Response.json({ code: "rate_limited", retry_after_seconds: limit.retryAfterSeconds }, {
      headers: { "cache-control": "no-store", "retry-after": String(limit.retryAfterSeconds) },
      status: 429,
    });
  }
  const hasGithubAttribution = await githubAttributionAvailable(env);
  const rows = cursor === null
    ? await firstPage(env, hasGithubAttribution)
    : await pageAfter(env, cursor, hasGithubAttribution);
  const page = rows.slice(0, PAGE_SIZE);
  const last = page[page.length - 1];
  const response = Response.json({
    next_cursor: rows.length > PAGE_SIZE && last !== undefined
      ? encodeCursor(text(last, "created_at"), text(last, "submission_id"))
      : null,
    submissions: page.map(publicLifecycleRow),
  }, { headers: { "cache-control": `public, max-age=0, s-maxage=${CACHE_SECONDS}` } });
  if (cache !== null) await cache.put(cacheKey, response.clone());
  return response;
}

async function firstPage(
  env: SubmissionApiEnv,
  hasGithubAttribution: boolean,
): Promise<readonly Record<string, unknown>[]> {
  const result = await env.DB.prepare(
    `${selectLifecycleRows(hasGithubAttribution)} order by created_at desc, submission_id asc limit ?`,
  )
    .bind(PAGE_SIZE + 1).all();
  return result.results;
}

async function pageAfter(
  env: SubmissionApiEnv,
  cursor: Cursor,
  hasGithubAttribution: boolean,
): Promise<readonly Record<string, unknown>[]> {
  const result = await env.DB.prepare(
    `${selectLifecycleRows(hasGithubAttribution)}
     where created_at < ? or (created_at = ? and submission_id > ?)
     order by created_at desc, submission_id asc limit ?`,
  ).bind(cursor.createdAt, cursor.createdAt, cursor.submissionId, PAGE_SIZE + 1).all();
  return result.results;
}

function selectLifecycleRows(hasGithubAttribution: boolean): string {
  return `select submission_id, declared_model_slug, submitter_display_name,
    ${hasGithubAttribution ? "github_login" : "null as github_login"}, status, publish_state,
    status_reason, created_at, validated_at, published_at from submissions`;
}

function publicLifecycleRow(row: Record<string, unknown>) {
  const status = text(row, "status");
  const reason = nullableText(row, "status_reason");
  return {
    created_at: d1TimestampToIso(text(row, "created_at")),
    declared_model_slug: nullableText(row, "declared_model_slug"),
    publish_state: text(row, "publish_state"),
    ...(status === "rejected" ? { reason_code: reason !== null && rejectionReasons.has(reason) ? reason : null } : {}),
    published_at: nullableIso(row, "published_at"),
    status,
    submission_id: text(row, "submission_id"),
    submitter_display_name: nullableText(row, "submitter_display_name"),
    github_login: nullableText(row, "github_login"),
    validated_at: nullableIso(row, "validated_at"),
  };
}

function encodeCursor(createdAt: string, submissionId: string): string {
  return btoa(`${createdAt}\n${submissionId}`).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function decodeCursor(value: string): Cursor | null {
  try {
    const padded = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
    const [createdAt, submissionId, extra] = atob(padded).split("\n");
    if (createdAt === undefined || submissionId === undefined || extra !== undefined || createdAt.length === 0 || submissionId.length === 0) {
      return null;
    }
    return { createdAt, submissionId };
  } catch (error) {
    if (error instanceof DOMException) return null;
    throw error;
  }
}

function edgeCache(): Cache | null {
  const value = (globalThis as typeof globalThis & { readonly caches?: CacheStorage & { readonly default?: Cache } }).caches;
  return value?.default ?? null;
}

function nullableIso(row: Record<string, unknown>, key: string): string | null {
  const value = nullableText(row, key);
  return value === null ? null : d1TimestampToIso(value);
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? `${value.slice(0, 10)}T${value.slice(11)}Z` : value;
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") throw new Error(`${key} must be a string`);
  return value;
}

function nullableText(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value === null || typeof value === "string") return value;
  throw new Error(`${key} must be a string or null`);
}

import type { SubmissionApiEnv } from "./submission-contracts";
import { clientIp } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";
import { listPendingVerificationQueue } from "./submission-store";

export const PENDING_VERIFICATION_COHORT_CAP = 5;
const QUEUE_CACHE_SECONDS = 60;
const QUEUE_MISSES_PER_IP_PER_MINUTE = 30;

export async function handlePendingVerificationQueue(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const cache = edgeCache();
  const cacheKey = new Request(new URL("/api/submissions/queue", request.url));
  const cached = cache === null ? undefined : await cache.match(cacheKey);
  if (cached !== undefined) return cached;
  const limit = await rateLimited(env, `queue:ip:${clientIp(request)}`, QUEUE_MISSES_PER_IP_PER_MINUTE, 60);
  if (limit.limited) {
    return Response.json({ code: "rate_limited", retry_after_seconds: limit.retryAfterSeconds }, {
      headers: { "cache-control": "no-store", "retry-after": String(limit.retryAfterSeconds) },
      status: 429,
    });
  }
  const queue = await listPendingVerificationQueue(env, PENDING_VERIFICATION_COHORT_CAP);
  const response = Response.json({
    cohort_cap: PENDING_VERIFICATION_COHORT_CAP,
    policy: "fifo_exact_gguf_maintainer_agentic_verification",
    submissions: queue.rows.map((row, index) => ({
      declared_model_slug: catalogSlugOrNull(row.declared_model_slug),
      position: index + 1,
      queued_at: d1TimestampToIso(row.queued_at),
      submission_id: row.submission_id,
      suite_release_id: row.suite_release_id,
    })),
    total_pending: queue.totalPending,
  }, { headers: { "cache-control": `public, max-age=0, s-maxage=${QUEUE_CACHE_SECONDS}` } });
  if (cache !== null) await cache.put(cacheKey, response.clone());
  return response;
}

function edgeCache(): Cache | null {
  const value = (globalThis as typeof globalThis & { readonly caches?: CacheStorage & { readonly default?: Cache } }).caches;
  return value?.default ?? null;
}

function catalogSlugOrNull(value: string | null): string | null {
  return value !== null && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) && value.length <= 120 ? value : null;
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.slice(0, 10)}T${value.slice(11)}Z`
    : value;
}

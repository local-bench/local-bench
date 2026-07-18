import type { D1DatabaseBinding } from "./submission-contracts";

type RateLimitEnv = {
  readonly DB: D1DatabaseBinding;
};

export type RateLimitResult =
  | { readonly limited: false }
  | { readonly limited: true; readonly retryAfterSeconds: number };

export type RateBudget = {
  readonly amount: number;
  readonly key: string;
  readonly limit: number;
  readonly windowSeconds: number;
};

// Race-safe fixed-window counter: the read-modify-write is a SINGLE atomic upsert,
// so concurrent requests cannot both observe capacity and both proceed (formerly a
// SELECT-then-UPDATE that two callers could interleave). The upsert always applies
// the increment and RETURNs the new count; the caller decides limited from that,
// which yields exactly `limit` non-limited responses per window under concurrency.
export async function consumeRateBudget(env: RateLimitEnv, budget: RateBudget): Promise<RateLimitResult> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % budget.windowSeconds);
  const windowStart = new Date(windowStartSeconds * 1000).toISOString();
  const retryAfterSeconds = Math.max(windowStartSeconds + budget.windowSeconds - nowSeconds, 1);
  if (budget.amount > budget.limit) return { limited: true, retryAfterSeconds };
  const row = await env.DB.prepare(
    `insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)
     on conflict(bucket_key) do update set
       window_start = ?,
       count = (case when rate_counters.window_start = ? then rate_counters.count else 0 end) + ?
     returning count`,
  ).bind(budget.key, windowStart, budget.amount, windowStart, windowStart, budget.amount).first();
  const count = typeof row?.["count"] === "number" ? row["count"] : budget.amount;
  return count > budget.limit ? { limited: true, retryAfterSeconds } : { limited: false };
}

export async function rateLimited(
  env: RateLimitEnv,
  key: string,
  limit: number,
  windowSeconds: number,
): Promise<RateLimitResult> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % windowSeconds);
  const windowStart = new Date(windowStartSeconds * 1000).toISOString();
  const retryAfterSeconds = Math.max(windowStartSeconds + windowSeconds - nowSeconds, 1);
  const row = await env.DB.prepare(
    `insert into rate_counters (bucket_key, window_start, count) values (?, ?, 1)
     on conflict(bucket_key) do update set
       window_start = ?,
       count = (case when rate_counters.window_start = ? then rate_counters.count else 0 end) + 1
     returning count`,
  )
    .bind(key, windowStart, windowStart, windowStart)
    .first();
  const count = typeof row?.["count"] === "number" ? row["count"] : 1;
  return count > limit ? { limited: true, retryAfterSeconds } : { limited: false };
}

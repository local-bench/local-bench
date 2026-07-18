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

export async function consumeRateBudget(env: RateLimitEnv, budget: RateBudget): Promise<RateLimitResult> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % budget.windowSeconds);
  const windowStart = new Date(windowStartSeconds * 1000).toISOString();
  const retryAfterSeconds = Math.max(windowStartSeconds + budget.windowSeconds - nowSeconds, 1);
  const existing = await env.DB.prepare("select window_start, count from rate_counters where bucket_key = ?")
    .bind(budget.key).first();
  if (existing === null || existing["window_start"] !== windowStart) {
    if (budget.amount > budget.limit) return { limited: true, retryAfterSeconds };
    await env.DB.prepare(
      "insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?) on conflict(bucket_key) do update set window_start = excluded.window_start, count = excluded.count",
    ).bind(budget.key, windowStart, budget.amount).run();
    return { limited: false };
  }
  const count = typeof existing["count"] === "number" ? existing["count"] : 0;
  if (count + budget.amount > budget.limit) return { limited: true, retryAfterSeconds };
  await env.DB.prepare("update rate_counters set count = count + ? where bucket_key = ?")
    .bind(budget.amount, budget.key).run();
  return { limited: false };
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
  const existing = await env.DB.prepare("select window_start, count from rate_counters where bucket_key = ?")
    .bind(key)
    .first();
  const retryAfterSeconds = Math.max(windowStartSeconds + windowSeconds - nowSeconds, 1);
  if (existing === null || existing["window_start"] !== windowStart) {
    await env.DB.prepare(
      "insert into rate_counters (bucket_key, window_start, count) values (?, ?, 1) on conflict(bucket_key) do update set window_start = excluded.window_start, count = 1",
    )
      .bind(key, windowStart)
      .run();
    return { limited: false };
  }
  const count = typeof existing["count"] === "number" ? existing["count"] : 0;
  if (count >= limit) {
    return { limited: true, retryAfterSeconds };
  }
  await env.DB.prepare("update rate_counters set count = count + 1 where bucket_key = ?")
    .bind(key)
    .run();
  return { limited: false };
}

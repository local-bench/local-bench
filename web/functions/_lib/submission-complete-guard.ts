import { clientIp, isSyntaxError } from "./submission-api-common";
import type { SubmissionApiEnv, SubmissionRow } from "./submission-contracts";
import { consumeRateBudget } from "./submission-rate-limit";

const MAX_COMPLETION_BODY_BYTES = 512 * 1024;
const COMPLETIONS_PER_IP_PER_HOUR = 120;
const COMPLETIONS_PER_SUBMISSION_PER_HOUR = 20;

export type CompletionBody =
  | { readonly kind: "ok"; readonly value: unknown }
  | { readonly kind: "invalid" }
  | { readonly kind: "too_large" };

export async function readCompletionBody(request: Request): Promise<CompletionBody> {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    const declaredLength = Number(contentLength);
    if (Number.isFinite(declaredLength) && declaredLength > MAX_COMPLETION_BODY_BYTES) {
      return { kind: "too_large" };
    }
  }
  if (request.body === null) return { kind: "invalid" };
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let bytesRead = 0;
  let text = "";
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    bytesRead += chunk.value.byteLength;
    if (bytesRead > MAX_COMPLETION_BODY_BYTES) {
      await reader.cancel("completion_body_too_large");
      return { kind: "too_large" };
    }
    text += decoder.decode(chunk.value, { stream: true });
  }
  text += decoder.decode();
  try {
    const value: unknown = JSON.parse(text);
    return { kind: "ok", value };
  } catch (error) {
    if (isSyntaxError(error)) return { kind: "invalid" };
    throw error;
  }
}

export async function completionRateLimit(
  request: Request,
  env: SubmissionApiEnv,
  row: SubmissionRow,
): Promise<Response | null> {
  const budgets = await Promise.all([
    consumeRateBudget(env, {
      amount: 1,
      key: `complete:ip:${clientIp(request)}`,
      limit: COMPLETIONS_PER_IP_PER_HOUR,
      windowSeconds: 60 * 60,
    }),
    consumeRateBudget(env, {
      amount: 1,
      key: `complete:submission:${row.submission_id}`,
      limit: COMPLETIONS_PER_SUBMISSION_PER_HOUR,
      windowSeconds: 60 * 60,
    }),
  ]);
  const limited = budgets.filter((budget) => budget.limited);
  if (limited.length === 0) return null;
  const retryAfterSeconds = Math.max(...limited.map((budget) => budget.retryAfterSeconds));
  return Response.json({ code: "rate_limited", retry_after_seconds: retryAfterSeconds }, {
    headers: { "cache-control": "no-store", "retry-after": String(retryAfterSeconds) },
    status: 429,
  });
}

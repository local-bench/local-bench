import { z } from "zod";
import { clientIp, isSyntaxError } from "./submission-api-common";
import { jsonResponse, adminBlocked } from "./submission-api-support";
import { rateLimited } from "./submission-rate-limit";
import type { D1DatabaseBinding } from "./submission-contracts";

type SendEmailBinding = {
  send(message: { readonly subject: string; readonly text: string }): Promise<unknown> | unknown;
};

export type FeedbackApiEnv = {
  readonly ADMIN_API_SECRET?: string;
  readonly DB: D1DatabaseBinding;
  readonly FEEDBACK_EMAIL?: SendEmailBinding;
  readonly FEEDBACK_IP_SALT?: string;
  readonly FEEDBACK_NTFY_URL?: string;
  readonly TURNSTILE_ENABLED?: string;
};

type FeedbackRouteParams = {
  readonly id?: string;
};

type WaitUntilContext = {
  waitUntil(promise: Promise<unknown>): void;
};

const FeedbackRequestSchema = z.object({
  contact: z.string().max(200).optional(),
  message: z.string().min(10).max(4000),
});
const RawFeedbackRequestSchema = z.object({
  contact: z.string().optional(),
  message: z.string(),
});
const FeedbackStatusSchema = z.enum(["new", "read"]);
const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/g;

export async function handleCreateFeedback(
  request: Request,
  env: FeedbackApiEnv,
  context?: WaitUntilContext,
): Promise<Response> {
  if (turnstileEnabled(env)) {
    return jsonResponse(503, {
      code: "turnstile_not_configured",
      error: "turnstile enforcement is not configured",
    });
  }
  const salt = (env.FEEDBACK_IP_SALT ?? "").trim();
  if (salt.length === 0) {
    return jsonResponse(503, { code: "feedback_not_configured", error: "feedback is not configured" });
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch (error) {
    if (isSyntaxError(error)) {
      return invalidFeedback();
    }
    throw error;
  }
  const parsed = RawFeedbackRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return invalidFeedback();
  }
  const message = stripControlChars(parsed.data.message).trim();
  const contact = stripControlChars(parsed.data.contact ?? "").trim();
  const cleaned = FeedbackRequestSchema.safeParse({ contact, message });
  if (!cleaned.success) {
    return invalidFeedback();
  }
  const ipHash = await sha256Hex(`${clientIp(request)}:${salt}`);
  const limited = await firstRateLimit(env, [
    [`feedback:ip:${ipHash}:hour`, 5, 60 * 60, "ip_hour"],
    [`feedback:ip:${ipHash}:day`, 20, 24 * 60 * 60, "ip_day"],
    ["feedback:global:day", 200, 24 * 60 * 60, "global_day"],
  ]);
  if (limited !== null) {
    return jsonResponse(429, {
      code: "rate_limited",
      error: "rate limited",
      retry_after_seconds: limited.retryAfterSeconds,
      scope: limited.scope,
    });
  }
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  await env.DB.prepare(
    "insert into feedback (id, message, contact, created_at, ip_hash, status) values (?, ?, ?, ?, ?, 'new')",
  )
    .bind(id, message, contact === "" ? null : contact, createdAt, ipHash)
    .run();
  scheduleNotification(env, context, { contact, createdAt, id, message });
  return jsonResponse(201, { id, status: "new" });
}

export async function handleAdminListFeedback(request: Request, env: FeedbackApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const url = new URL(request.url);
  const parsedStatus = FeedbackStatusSchema.safeParse(url.searchParams.get("status") ?? "new");
  if (!parsedStatus.success) {
    return jsonResponse(400, { code: "invalid_feedback_status", error: "invalid feedback status" });
  }
  const requestedLimit = Number(url.searchParams.get("limit") ?? "50");
  const limit = Number.isFinite(requestedLimit) ? Math.min(Math.max(Math.floor(requestedLimit), 1), 100) : 50;
  const rows = await env.DB.prepare(
    "select id, message, contact, created_at, status from feedback where status = ? order by created_at desc limit ?",
  )
    .bind(parsedStatus.data, limit)
    .all();
  return jsonResponse(200, { feedback: rows.results });
}

export async function handleAdminMarkFeedbackRead(
  request: Request,
  env: FeedbackApiEnv,
  params: FeedbackRouteParams,
): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const id = params.id ?? "";
  if (id.length === 0) {
    return jsonResponse(400, { code: "missing_feedback_id", error: "feedback id route param missing" });
  }
  const existing = await env.DB.prepare("select id from feedback where id = ?").bind(id).first();
  if (existing === null) {
    return jsonResponse(404, { code: "unknown_feedback", error: "unknown feedback" });
  }
  await env.DB.prepare("update feedback set status = 'read' where id = ?").bind(id).run();
  return jsonResponse(200, { id, status: "read" });
}

function invalidFeedback(): Response {
  return jsonResponse(400, { code: "invalid_feedback", error: "invalid feedback" });
}

function stripControlChars(value: string): string {
  return value.replace(CONTROL_CHARS, "");
}

async function firstRateLimit(
  env: FeedbackApiEnv,
  checks: readonly (readonly [key: string, limit: number, windowSeconds: number, scope: string])[],
): Promise<{ readonly retryAfterSeconds: number; readonly scope: string } | null> {
  for (const [key, limit, windowSeconds, scope] of checks) {
    const result = await rateLimited(env, key, limit, windowSeconds);
    if (result.limited) {
      return { retryAfterSeconds: result.retryAfterSeconds, scope };
    }
  }
  return null;
}

function scheduleNotification(
  env: FeedbackApiEnv,
  context: WaitUntilContext | undefined,
  feedback: { readonly contact: string; readonly createdAt: string; readonly id: string; readonly message: string },
): void {
  const task = notifyMaintainer(env, feedback).catch(() => undefined);
  if (context === undefined) {
    return;
  }
  context.waitUntil(task);
}

async function notifyMaintainer(
  env: FeedbackApiEnv,
  feedback: { readonly contact: string; readonly createdAt: string; readonly id: string; readonly message: string },
): Promise<void> {
  const text = notificationText(feedback);
  const jobs: Promise<unknown>[] = [];
  const ntfyUrl = (env.FEEDBACK_NTFY_URL ?? "").trim();
  if (ntfyUrl.length > 0) {
    jobs.push(fetch(ntfyUrl, { body: text, headers: { "content-type": "text/plain; charset=utf-8" }, method: "POST" }));
  }
  if (env.FEEDBACK_EMAIL !== undefined) {
    jobs.push(Promise.resolve(env.FEEDBACK_EMAIL.send({ subject: "local-bench feedback", text })));
  }
  await Promise.allSettled(jobs);
}

function notificationText(feedback: {
  readonly contact: string;
  readonly createdAt: string;
  readonly id: string;
  readonly message: string;
}): string {
  const contact = feedback.contact === "" ? "n/a" : feedback.contact;
  const message = feedback.message.length > 1200 ? `${feedback.message.slice(0, 1200)}...` : feedback.message;
  return [`Feedback ${feedback.id}`, feedback.createdAt, `Contact: ${contact}`, "", message].join("\n");
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function turnstileEnabled(env: Pick<FeedbackApiEnv, "TURNSTILE_ENABLED">): boolean {
  return (env.TURNSTILE_ENABLED ?? "").toLowerCase() === "true";
}

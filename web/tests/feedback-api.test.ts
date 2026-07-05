import { describe, expect, it, vi } from "vitest";
import { handleAdminListFeedback, handleAdminMarkFeedbackRead, handleCreateFeedback, type FeedbackApiEnv } from "../functions/_lib/feedback-api";
import {
  ADMIN_SECRET,
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0007,
  createEnv,
  getRequest,
  jsonRequest,
  tableExists,
} from "./submission-test-support";

async function feedbackEnv(overrides: Partial<FeedbackApiEnv> = {}): Promise<FeedbackApiEnv> {
  const env = await createEnv({
    includeAdminSecret: true,
    includeR2Secrets: false,
    migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0007],
  });
  return { ...env, FEEDBACK_IP_SALT: "test-salt", ...overrides };
}

async function responseJson(response: Response): Promise<Record<string, unknown>> {
  const body: unknown = await response.json();
  if (!isRecord(body)) {
    throw new Error("response was not a JSON object");
  }
  return body;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function feedbackRequest(message: string, contact = "", ip = "203.0.113.8"): Request {
  return jsonRequest("/api/feedback", { contact, message }, { "CF-Connecting-IP": ip });
}

describe("feedback API", () => {
  it("applies the feedback migration", async () => {
    const env = await feedbackEnv();
    expect(await tableExists(env.DB, "feedback")).toBe(true);
  });

  it("validates and stores sanitized feedback", async () => {
    const env = await feedbackEnv();
    const invalid = await handleCreateFeedback(feedbackRequest("too short"), env);
    expect(invalid.status).toBe(400);

    const response = await handleCreateFeedback(feedbackRequest("This is a useful note\u0000 about the benchmark.", "me@example.test\u0007"), env);
    expect(response.status).toBe(201);
    const row = await env.DB.prepare("select message, contact, ip_hash, status from feedback").first();
    expect(row).toMatchObject({
      contact: "me@example.test",
      message: "This is a useful note about the benchmark.",
      status: "new",
    });
    expect(typeof row?.["ip_hash"]).toBe("string");
    expect(String(row?.["ip_hash"])).toHaveLength(64);
  });

  it("honors Turnstile enablement like submission endpoints", async () => {
    const env = await feedbackEnv({ TURNSTILE_ENABLED: "true" });
    const response = await handleCreateFeedback(feedbackRequest("This should be blocked."), env);
    expect(response.status).toBe(503);
    await expect(responseJson(response)).resolves.toMatchObject({ code: "turnstile_not_configured" });
  });

  it("rate-limits per IP and globally", async () => {
    const env = await feedbackEnv();
    for (let index = 0; index < 5; index += 1) {
      const response = await handleCreateFeedback(feedbackRequest(`Hourly limited message ${index}`), env);
      expect(response.status).toBe(201);
    }
    const hourly = await handleCreateFeedback(feedbackRequest("Hourly limited message final"), env);
    expect(hourly.status).toBe(429);
    await expect(responseJson(hourly)).resolves.toMatchObject({ code: "rate_limited", scope: "ip_hour" });

    const globalEnv = await feedbackEnv();
    await seedRateCounter(globalEnv, "feedback:global:day", 200, 24 * 60 * 60);
    const global = await handleCreateFeedback(feedbackRequest("Global limited message final", "", "192.0.2.250"), globalEnv);
    expect(global.status).toBe(429);
    await expect(responseJson(global)).resolves.toMatchObject({ code: "rate_limited", scope: "global_day" });
  }, 15_000);

  it("does not fail the request when notification delivery fails", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("notification failed"));
    const env = await feedbackEnv({ FEEDBACK_NTFY_URL: "https://notify.invalid/localbench" });
    const response = await handleCreateFeedback(feedbackRequest("Notification failure should still store."), env);
    expect(response.status).toBe(201);
    expect(fetchSpy).toHaveBeenCalledOnce();
    fetchSpy.mockRestore();
  });

  it("supports admin listing and marking feedback read", async () => {
    const env = await feedbackEnv();
    const create = await handleCreateFeedback(feedbackRequest("Please consider showing decode speed."), env);
    const created = await responseJson(create);
    const id = String(created["id"]);

    const unauthorized = await handleAdminListFeedback(getRequest("/api/admin/feedback?status=new"), env);
    expect(unauthorized.status).toBe(401);

    const list = await handleAdminListFeedback(
      getRequest("/api/admin/feedback?status=new", { "x-localbench-admin-secret": ADMIN_SECRET }),
      env,
    );
    expect(list.status).toBe(200);
    const listBody = await responseJson(list);
    expect(listBody["feedback"]).toEqual([
      expect.objectContaining({ id, message: "Please consider showing decode speed.", status: "new" }),
    ]);

    const read = await handleAdminMarkFeedbackRead(
      jsonRequest(`/api/admin/feedback/${id}/read`, {}, { "x-localbench-admin-secret": ADMIN_SECRET }),
      env,
      { id },
    );
    expect(read.status).toBe(200);
    const readRows = await handleAdminListFeedback(
      getRequest("/api/admin/feedback?status=read", { "x-localbench-admin-secret": ADMIN_SECRET }),
      env,
    );
    const readBody = await responseJson(readRows);
    expect(readBody["feedback"]).toEqual([expect.objectContaining({ id, status: "read" })]);
  });
});

async function seedRateCounter(env: FeedbackApiEnv, key: string, count: number, windowSeconds: number): Promise<void> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStartSeconds = nowSeconds - (nowSeconds % windowSeconds);
  const windowStart = new Date(windowStartSeconds * 1000).toISOString();
  await env.DB.prepare("insert into rate_counters (bucket_key, window_start, count) values (?, ?, ?)")
    .bind(key, windowStart, count)
    .run();
}

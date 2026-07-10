import { describe, expect, it } from "vitest";
import { onRequestGet } from "../functions/api/submissions/queue";
import { parseQueue } from "../components/pending-verification-queue";
import { createEnv } from "./submission-test-support";

describe("pending verification queue", () => {
  it("returns only the first five pending tickets in FIFO order with honest positions", async () => {
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: false });
    for (let index = 0; index < 7; index += 1) {
      const suffix = String(index).padStart(2, "0");
      await env.DB.prepare(
        `insert into submissions (
          submission_id, origin, submitter_id, ticket_id, status, raw_bundle_sha256,
          idempotency_key, publish_state, declared_model_slug, created_at, uploaded_at
        ) values (?, 'community', ?, ?, 'pending_verification', ?, ?, 'hidden', ?, ?, ?)`,
      )
        .bind(
          `ticket_${suffix}`,
          `public_key:${suffix}`,
          `ticket_${suffix}`,
          suffix.repeat(32),
          suffix.repeat(32),
          index === 0 ? "Vendor / Fake" : index === 1 ? "qwen3-0-6b" : `model-${suffix}`,
          `2026-07-10 00:00:${suffix}`,
          `2026-07-10 00:00:${suffix}`,
        )
        .run();
    }

    const response = await onRequestGet({ env, request: new Request("https://local-bench.ai/api/submissions/queue") });
    const payload = parseQueue(await response.json());

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("public, max-age=0, s-maxage=60");
    expect(payload.cohort_cap).toBe(5);
    expect(payload.total_pending).toBe(7);
    expect(payload.submissions.map((ticket) => ticket.position)).toEqual([1, 2, 3, 4, 5]);
    expect(payload.submissions.map((ticket) => ticket.model_label)).toEqual([
      "Pending submission · ticket00",
      "Qwen3 0.6B",
      "Pending submission · ticket02",
      "Pending submission · ticket03",
      "Pending submission · ticket04",
    ]);
    expect(payload.submissions[0]).not.toHaveProperty("submitter_display_name");
    expect(payload.submissions[0]).not.toHaveProperty("declared_model_slug");
  });

  it("rejects malformed client payloads instead of rendering invented queue data", () => {
    expect(() => parseQueue({ cohort_cap: 5, submissions: "nope", total_pending: 1 })).toThrow(
      "invalid pending queue payload",
    );
  });
});

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
          `model-${suffix}`,
          `2026-07-10 00:00:${suffix}`,
          `2026-07-10 00:00:${suffix}`,
        )
        .run();
    }

    const response = await onRequestGet({ env });
    const payload = parseQueue(await response.json());

    expect(response.status).toBe(200);
    expect(payload.cohort_cap).toBe(5);
    expect(payload.total_pending).toBe(7);
    expect(payload.submissions.map((ticket) => ticket.position)).toEqual([1, 2, 3, 4, 5]);
    expect(payload.submissions.map((ticket) => ticket.declared_model_slug)).toEqual([
      "model-00",
      "model-01",
      "model-02",
      "model-03",
      "model-04",
    ]);
  });

  it("rejects malformed client payloads instead of rendering invented queue data", () => {
    expect(() => parseQueue({ cohort_cap: 5, submissions: "nope", total_pending: 1 })).toThrow(
      "invalid pending queue payload",
    );
  });
});

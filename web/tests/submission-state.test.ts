import { describe, expect, it } from "vitest";
import {
  ALLOWED_SUBMISSION_TRANSITIONS,
  SUBMISSION_STATUSES,
  assertTransition,
  isSubmissionStatus,
} from "../functions/_lib/submission-state";

describe("submission state machine", () => {
  it("allows every declared ZT-0 lifecycle transition", () => {
    // Given: the approved ZT-0 status vocabulary and transition map.
    const allowed = Object.entries(ALLOWED_SUBMISSION_TRANSITIONS);

    // When / Then: every target in the map is accepted by the shared assertion.
    for (const [from, targets] of allowed) {
      for (const to of targets) {
        expect(() => assertTransition(from, to)).not.toThrow();
      }
    }
  });

  it("rejects representative forbidden lifecycle transitions with a typed conflict", () => {
    // Given: transitions that skip moderation, leave terminal states, or republish a removed row.
    const forbidden = [
      ["ticketed", "accepted"],
      ["pending_verification", "suppressed"],
      ["accepted", "rejected"],
      ["rejected", "accepted"],
      ["withdrawn", "accepted"],
      ["suppressed", "published"],
      ["expired", "pending_verification"],
    ] as const;

    // When / Then: the shared assertion rejects each one with the public error code.
    for (const [from, to] of forbidden) {
      expect(() => assertTransition(from, to)).toThrowError(
        expect.objectContaining({ code: "invalid_transition", from, to }),
      );
    }
  });

  it("keeps the runtime status parser aligned with the exported vocabulary", () => {
    // Given / When / Then: every exported status is recognized and unknown legacy junk is not.
    for (const status of SUBMISSION_STATUSES) {
      expect(isSubmissionStatus(status)).toBe(true);
    }
    expect(isSubmissionStatus("published")).toBe(false);
  });
});

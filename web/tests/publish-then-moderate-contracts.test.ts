import { describe, expect, it } from "vitest";
import {
  AcceptedResultProjectionV2Schema,
  REJECTION_REASON_CODES,
  StatusUpdateSchema,
} from "../functions/_lib/submission-contracts";
import { RAW_BUNDLE_SHA, statusUpdate } from "./submission-test-support";

describe("publish-then-moderate verification contracts", () => {
  it("accepts a projection-free rejected decision and rejects projection fields", () => {
    const rejected = {
      accepted: false,
      operation: "initial_decision",
      raw_bundle_sha256: "a".repeat(64),
      reason_code: "manifest_invalid",
      reason_detail: "synthetic fixture manifest is invalid",
      status: "rejected",
      validated_at: "2026-07-18T00:00:00Z",
      validator_commit: "fixture-commit",
      validator_version: "fixture-validator",
    };

    expect(StatusUpdateSchema.safeParse(rejected).success).toBe(true);
    expect(StatusUpdateSchema.safeParse({ ...rejected, projection: {} }).success).toBe(false);
  });

  it("enforces the bounded rejection reason vocabulary and safe detail text", () => {
    expect(REJECTION_REASON_CODES).toContain("metadata_unsafe");
    const rejected = {
      accepted: false,
      operation: "initial_decision",
      raw_bundle_sha256: "b".repeat(64),
      reason_code: "not_a_reason",
      status: "rejected",
      validated_at: "2026-07-18T00:00:00Z",
      validator_version: "fixture-validator",
    };
    expect(StatusUpdateSchema.safeParse(rejected).success).toBe(false);
    expect(StatusUpdateSchema.safeParse({
      ...rejected,
      reason_code: "internal_error",
      reason_detail: "bad\u0000detail",
    }).success).toBe(false);
  });

  it("requires explicit refresh concurrency guards", () => {
    const accepted = statusUpdate("accepted");
    const missingOperation = { ...accepted };
    delete missingOperation["operation"];
    expect(StatusUpdateSchema.safeParse(missingOperation).success).toBe(false);
    expect(StatusUpdateSchema.safeParse({
      ...accepted,
      operation: "projection_refresh",
    }).success).toBe(false);
    expect(StatusUpdateSchema.safeParse({
      ...accepted,
      expected_state_revision: 4,
      operation: "projection_refresh",
      previous_projection_object_sha256: "c".repeat(64),
    }).success).toBe(true);
  });

  it("rejects overlong and control-bearing projection strings", () => {
    const accepted = statusUpdate("accepted");
    const projection = accepted["projection"];
    expect(typeof projection === "object" && projection !== null).toBe(true);
    if (typeof projection !== "object" || projection === null) return;
    const model = "model" in projection ? projection.model : null;
    expect(typeof model === "object" && model !== null).toBe(true);
    if (typeof model !== "object" || model === null) return;

    expect(StatusUpdateSchema.safeParse({
      ...accepted,
      operation: "initial_decision",
      projection: { ...projection, model: { ...model, display_name: "x".repeat(121) } },
    }).success).toBe(false);
    expect(StatusUpdateSchema.safeParse({
      ...accepted,
      operation: "initial_decision",
      projection: { ...projection, model: { ...model, family: "unsafe\u202Etext" } },
    }).success).toBe(false);
  });
});


describe("projection unsafe-text deep scan", () => {
  it("accepts multi-line build_flags but still rejects bidi values and control keys", () => {
    const base = statusUpdate("accepted", RAW_BUNDLE_SHA, "community")["projection"] as Record<string, unknown>;
    const runtime = { ...(base["runtime"] as Record<string, unknown>) };

    runtime["build_flags"] = "version: 1 (38c66ad)\nbuilt with MSVC 19.44\tfor Windows AMD64";
    expect(AcceptedResultProjectionV2Schema.safeParse({ ...base, runtime }).success).toBe(true);

    runtime["build_flags"] = "version ‮ reversed";
    expect(AcceptedResultProjectionV2Schema.safeParse({ ...base, runtime }).success).toBe(false);

    runtime["build_flags"] = "version 1";
    const poisonedKey = { ...base, runtime, ["bad\nkey"]: "x" };
    expect(AcceptedResultProjectionV2Schema.safeParse(poisonedKey).success).toBe(false);
  });
});

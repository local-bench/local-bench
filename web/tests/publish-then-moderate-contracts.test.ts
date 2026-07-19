import { describe, expect, it } from "vitest";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { RAW_BUNDLE_SHA, statusUpdate } from "./submission-test-support";

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

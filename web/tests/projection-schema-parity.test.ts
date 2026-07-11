import { describe, expect, it } from "vitest";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { statusUpdate } from "./submission-test-support";

describe("accepted projection v2 TypeScript/JSON-schema parity", () => {
  it("rejects duplicate lineage.base_model values at Worker acceptance", () => {
    const update: any = statusUpdate("accepted", "a".repeat(64), "community");
    update.projection.lineage.base_model = ["Org/Base", "Org/Base"];
    expect(AcceptedResultProjectionV2Schema.safeParse(update.projection).success).toBe(false);
  });

  // Parity sweep checked the canonical schema's required fields, strict object shapes,
  // scalar bounds/nullability, enums/constants, digest/model-system patterns, tuple
  // cardinality, axes minProperties, suite/digest conditionals, community identity
  // conditionals, and lineage uniqueItems. uniqueItems was the only remaining mismatch.
  it("retains acceptance for the canonical unique-lineage fixture", () => {
    const update: any = statusUpdate("accepted", "a".repeat(64), "community");
    update.projection.lineage.base_model = ["Org/Base", "Org/Other"];
    expect(AcceptedResultProjectionV2Schema.safeParse(update.projection).success).toBe(true);
  });
});

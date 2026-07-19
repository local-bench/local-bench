import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  ACCEPTED_PROJECTION_INDEX_VERSIONS,
  ACCEPTED_PROJECTION_RESCORE_MODE_KEYS,
  ACCEPTED_PROJECTION_SUITE_RELEASE_IDS,
  AcceptedResultProjectionV2Schema,
} from "../functions/_lib/submission-contracts";
import { statusUpdate } from "./submission-test-support";

describe("accepted projection v2 TypeScript/JSON-schema parity", () => {
  it("locks Worker season identity and split-bench provenance to the canonical CLI schema", () => {
    const canonical = JSON.parse(readFileSync(
      path.resolve(process.cwd(), "..", "cli", "src", "localbench", "submissions", "schemas", "accepted_result_projection_v2.schema.json"),
      "utf8",
    ));

    expect([...ACCEPTED_PROJECTION_SUITE_RELEASE_IDS]).toEqual(canonical.properties.suite_release_id.enum);
    expect([...ACCEPTED_PROJECTION_INDEX_VERSIONS]).toEqual(canonical.properties.index_version.enum);
    expect([...ACCEPTED_PROJECTION_RESCORE_MODE_KEYS]).toEqual(Object.keys(canonical.properties.rescore_modes.properties));
  });

  it("pins the season-2 manifest while accepting split-bench rescore provenance", () => {
    const update: any = statusUpdate("accepted", "a".repeat(64), "community");
    update.projection.suite_release_id = "suite-v2-full-exec-tooluse-5axis-v2";
    update.projection.suite_manifest_sha256 = "b".repeat(64);
    update.projection.index_version = "index-v4.0";
    update.projection.rescore_modes.bfcl_multi_turn_base = "rescored";
    update.projection.rescore_modes.bfcl_multi_turn_long_context = "verdict_carried";
    expect(AcceptedResultProjectionV2Schema.safeParse(update.projection).success).toBe(false);

    update.projection.suite_manifest_sha256 = "81420326194941f2dc2ec9146e5fc0dc06a8dca574b582a46ee6e0a1f7d1c734";
    expect(AcceptedResultProjectionV2Schema.safeParse(update.projection).success).toBe(true);
  });

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

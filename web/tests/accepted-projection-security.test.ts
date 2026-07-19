import { describe, expect, it } from "vitest";
import {
  AcceptedResultProjectionV2Schema,
  type AcceptedResultProjectionV2,
} from "../functions/_lib/accepted-result-projection-contract";
import { RAW_BUNDLE_SHA, completeProjection } from "./submission-test-support";

describe("accepted projection security bounds", () => {
  it("rejects axes outside the canonical suite allowlist", () => {
    // Given: an otherwise valid projection with an extra attacker-named axis.
    const projection = validProjection();
    const agentic = projection.axes.agentic;
    if (agentic === undefined) throw new Error("complete fixture must include agentic");

    // When: the projection contract parses the axis map.
    const result = AcceptedResultProjectionV2Schema.safeParse({
      ...projection,
      axes: { ...projection.axes, attacker_axis: agentic },
    });

    // Then: unknown axis names are rejected.
    expect(result.success).toBe(false);
  });

  it.each([
    ["an inverted confidence interval", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      axes: { ...projection.axes, agentic: { ci: [0.8, 0.6], n: 10, score: 0.7, status: "measured" } },
    })],
    ["a confidence interval excluding the score", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      axes: { ...projection.axes, agentic: { ci: [0.1, 0.2], n: 10, score: 0.7, status: "measured" } },
    })],
    ["a measured axis without a score", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      axes: { ...projection.axes, agentic: { ci: null, n: 10, score: null, status: "measured" } },
    })],
    ["a measured axis without samples", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      axes: { ...projection.axes, agentic: { ci: null, n: 0, score: 0.7, status: "measured" } },
    })],
    ["a not-measured axis with a score", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      axes: { ...projection.axes, agentic: { ci: null, n: 0, score: 0.7, status: "not_measured" } },
    })],
  ])("rejects %s", (_label, makeInvalid) => {
    // Given: one structurally inconsistent axis record.
    const projection = makeInvalid(validProjection());

    // When: the projection crosses the server boundary.
    const result = AcceptedResultProjectionV2Schema.safeParse(projection);

    // Then: status, score, n, and CI semantics are enforced together.
    expect(result.success).toBe(false);
  });

  it.each([
    ["rank scope length", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      scores: { ...projection.scores, rank_scope: "r".repeat(121) },
    })],
    ["provenance note count", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      provenance_notes: Array.from({ length: 129 }, () => "note"),
    })],
    ["conformance reason count", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      conformance: { ...projection.conformance, reasons: Array.from({ length: 33 }, () => "reason") },
    })],
    ["conformance bench count", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      conformance: {
        ...projection.conformance,
        per_bench: Object.fromEntries(Array.from({ length: 65 }, (_, index) => [`bench-${index}`, true])),
      },
    })],
    ["conformance nesting depth", (projection: AcceptedResultProjectionV2) => ({
      ...projection,
      conformance: { ...projection.conformance, per_bench: { bench: { a: { b: { c: { d: { e: true } } } } } } },
    })],
  ])("rejects projection content above the %s bound", (_label, makeInvalid) => {
    // Given: an otherwise valid projection exceeding one content bound.
    const projection = makeInvalid(validProjection());

    // When: the accepted projection schema parses it.
    const result = AcceptedResultProjectionV2Schema.safeParse(projection);

    // Then: the untrusted content is rejected before persistence or board rebuild.
    expect(result.success).toBe(false);
  });
});

function validProjection(): AcceptedResultProjectionV2 {
  return AcceptedResultProjectionV2Schema.parse(completeProjection(RAW_BUNDLE_SHA, "project_anchor"));
}

import { describe, expect, it } from "vitest";
import {
  acceptedProjectionToBoardEntry,
  type AcceptedResultProjectionV1,
} from "../lib/board-entry";

describe("accepted projection to board_entries row", () => {
  it("maps board-safe projection fields into the D1 pointer row", () => {
    // Given: an accepted_result_projection_v1 with partial 4-axis coverage.
    const projection = {
      artifact_hashes: {
        bundle_sha256: "d".repeat(64),
        projection_sha256: "e".repeat(64),
        public_artifact_manifest_sha256: "f".repeat(64),
      },
      axes: {
        coding: { ci: null, n: 129, score: 0.8527, status: "measured" },
        instruction_following: { ci: null, n: 294, score: 0.6871, status: "measured" },
        knowledge: { ci: null, n: 400, score: 0.7725, status: "measured" },
        tool_calling: { ci: null, n: 330, score: 0.7364, status: "measured" },
      },
      benches: {
        ifbench: { n_errors: 0, raw_accuracy: 0.6871 },
        lcb: { n_errors: 0, raw_accuracy: 0.8527 },
        mmlu_pro: { n_errors: 0, raw_accuracy: 0.7725 },
        tc_json_v1: { n_errors: 1, raw_accuracy: 0.7364 },
      },
      conformance: { status: "headline-comparable" },
      coverage_profile_id: "partial-text-code-4axis-v1",
      headline_complete: false,
      lane_id: "answer-only",
      model: {
        display_name: "Gemma 4 12B Q4",
        family: "gemma-4",
        file_sha256: "a".repeat(64),
        quant_label: "Q4_K_M",
      },
      origin: "project_anchor",
      runtime: {
        hardware_summary: "1x RTX 4090",
        name: "llama.cpp",
        version: "b1234",
      },
      schema_version: "localbench.accepted_result_projection.v1",
      scorecard_id: "scorecard-v2.1-fixture",
      scores: {
        headline_score: null,
        known_headline_contribution: 0.3737,
        measured_headline_weight: 0.5,
        missing_headline_weight: 0.5,
        partial_composite: 0.7473,
        rank_scope: "partial-text-code-4axis-v1",
      },
      suite_manifest_sha256: "c".repeat(64),
      suite_release_id: "suite-v1-partial-text-code-4axis-v1",
      tier: "standard",
      trust_label: "community_re_scored",
      validator: {
        validated_at: "2026-06-30T00:00:00Z",
        validator_version: "localbench.submission-validator.v1",
      },
      verification_level: "bundle_rescored",
      warnings: ["public projection only"],
    } satisfies AcceptedResultProjectionV1;

    // When: the projection is prepared for D1 board_entries insertion.
    const row = acceptedProjectionToBoardEntry(projection, {
      entryId: "entry_01",
      publishedAt: "2026-06-30T01:00:00Z",
      scopeRank: 12,
      submissionId: "sub_01",
      visibility: "preview",
    });

    // Then: D1 receives a pointer/index row, not scoring truth.
    expect(row).toMatchObject({
      axis_scores_json: JSON.stringify(projection.axes),
      bench_scores_json: JSON.stringify(projection.benches),
      bundle_sha256: "d".repeat(64),
      conformance_json: JSON.stringify(projection.conformance),
      coverage_profile_id: "partial-text-code-4axis-v1",
      entry_id: "entry_01",
      global_rank: null,
      headline_complete: 0,
      headline_score: null,
      model_display_name: "Gemma 4 12B Q4",
      n_errors: 1,
      n_scored: 1153,
      partial_composite: 0.7473,
      projection_sha256: "e".repeat(64),
      scope_rank: 12,
      submission_id: "sub_01",
      suite_release_id: "suite-v1-partial-text-code-4axis-v1",
      visibility: "preview",
      warning_count: 1,
    });
  });
});

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PartialCoverageBoard } from "../components/partial-coverage-board";
import { PartialCoverageDataSchema, partialCoverageRows } from "../lib/board-entry";
import { formatScore } from "../lib/format";

// A published partial-coverage submission: the 4-axis text+code profile (agentic not measured),
// scores on the 0-1 raw-accuracy scale exactly as the offline rescorer emits them.
const SAMPLE = {
  entries: [
    {
      identity: {
        entryId: "entry-1",
        publishedAt: null,
        scopeRank: null,
        submissionId: "sub-1",
        visibility: "preview",
      },
      projection: {
        artifact_hashes: { bundle_sha256: "a".repeat(64), projection_sha256: "b".repeat(64) },
        axes: {
          agentic: { score: null, n: 0, status: "not_measured" },
          coding: { score: 0.8527, n: 129, status: "measured" },
          instruction_following: { score: 0.6871, n: 294, status: "measured" },
          knowledge: { score: 0.7725, n: 400, status: "measured" },
          tool_calling: { score: 0.7364, n: 330, status: "measured" },
        },
        conformance: { status: "headline-comparable" },
        coverage_profile_id: "partial-text-code-4axis-v1",
        headline_complete: false,
        model: { display_name: "Gemma 4 12B QAT", family: "gemma-4", quant_label: "UD-Q4_K_XL" },
        origin: "project_anchor",
        runtime: { name: "llama.cpp", version: "b1234" },
        schema_version: "localbench.accepted_result_projection.v1",
        scorecard_id: "scorecard-xyz",
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
        trust_label: "community_re_scored",
        verification_level: "bundle_rescored",
      },
    },
  ],
};

describe("partial-coverage board", () => {
  it("validates + maps a published partial projection into an UNRANKED board row", () => {
    const rows = partialCoverageRows(PartialCoverageDataSchema.parse(SAMPLE));
    expect(rows).toHaveLength(1);
    const row = rows[0];
    if (row === undefined) {
      expect.fail("expected one mapped partial-coverage row");
      return;
    }
    expect(row.global_rank).toBeNull();
    expect(row.headline_score).toBeNull();
    expect(row.partial_composite).toBe(0.7473);
    expect(row.coverage_profile_id).toBe("partial-text-code-4axis-v1");
    expect(row.n_scored).toBe(1153); // 400 + 294 + 330 + 129 (+ 0 agentic)
  });

  it("renders an unranked partial row on the 0-100 board scale", () => {
    const rows = partialCoverageRows(PartialCoverageDataSchema.parse(SAMPLE));
    const html = renderToStaticMarkup(createElement(PartialCoverageBoard, { rows }));
    expect(html).toContain("Gemma 4 12B QAT");
    expect(html).toContain("partial-text-code-4axis-v1");
    expect(html).toContain("unranked");
    expect(html).toContain("Runtime");
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
    expect(html).toContain(formatScore(74.73)); // partial_composite 0.7473 -> 74.7
    expect(html).toContain(formatScore(77.25)); // knowledge 0.7725 -> 77.2
    expect(html).toContain("Knowledge");
  });

  it("renders a dash when partial runtime identity is absent", () => {
    const [row] = partialCoverageRows(PartialCoverageDataSchema.parse(SAMPLE));
    if (row === undefined) {
      expect.fail("expected one mapped partial-coverage row");
      return;
    }
    const html = renderToStaticMarkup(
      createElement(PartialCoverageBoard, {
        rows: [{ ...row, runtime_name: null, runtime_version: null }],
      }),
    );
    expect(html).toContain("—");
  });

  it("renders nothing when no partial submissions are published", () => {
    const html = renderToStaticMarkup(createElement(PartialCoverageBoard, { rows: [] }));
    expect(html).toBe("");
  });
});

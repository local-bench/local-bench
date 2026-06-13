import { describe, expect, it } from "vitest";
import {
  computeFrontierGapPercent,
  rankRigMatches,
  type RigMatchAnchor,
  type RigMatchCandidate,
} from "../lib/rig-match";

const ANCHORS = [
  { modelLabel: "Gemini 3.1 Pro", score: { point: 94, lo: 93, hi: 95 } },
  { modelLabel: "GPT-5.5", score: { point: 92, lo: 91, hi: 93 } },
] as const satisfies readonly RigMatchAnchor[];

const CANDIDATES = [
  candidate("oversized-q5", "Oversized 70B", "Q5_K_M", 38, 76, 73, 78, 18),
  candidate("qwen-q4", "Qwen3 32B", "Q4_K_M", 19, 72, 70, 74, 42),
  candidate("llama-q3", "Llama-3.3 70B", "Q3_K_M", 22, 69, 66, 72, 18),
  candidate("anchor", "GPT-5.5", null, null, 94, 93, 95, null, "anchor", "api-uncapped"),
] as const satisfies readonly RigMatchCandidate[];

describe("rig-match finder logic", () => {
  it("ranks only local runs that fit by conservative lower-bound score", () => {
    // Given mixed local and anchor rows, including one local row above the VRAM budget.
    // When matches are ranked for a 24 GB answer-only selection.
    const matches = rankRigMatches({
      anchors: ANCHORS,
      candidates: CANDIDATES,
      lane: "answer-only",
      quant: "any",
      vramGb: 24,
    });

    // Then anchors and oversized locals are excluded, and remaining rows sort by lower CI bound.
    expect(matches.map((match) => match.runId)).toEqual(["qwen-q4", "llama-q3"]);
    expect(matches[0]?.verdict).toBe("best-under-budget");
    expect(matches[1]?.verdict).toBe("needs-replication");
  });

  it("filters by selected quant before ranking fitted rows", () => {
    // Given fitted local rows at different quant labels.
    // When the user asks specifically for Q3_K_M.
    const matches = rankRigMatches({
      anchors: ANCHORS,
      candidates: CANDIDATES,
      lane: "answer-only",
      quant: "Q3_K_M",
      vramGb: 24,
    });

    // Then only that quant appears in the ranked output.
    expect(matches.map((match) => match.quantLabel)).toEqual(["Q3_K_M"]);
  });

  it("computes frontier gap against the top anchor score", () => {
    // Given a local run and two anchor ceiling references.
    const candidateScore = { point: 72, lo: 70, hi: 74 };

    // When its frontier gap is computed.
    const gap = computeFrontierGapPercent(candidateScore, ANCHORS);

    // Then the percentage uses the highest anchor point score as the ceiling.
    expect(gap).toBeCloseTo((72 / 94) * 100, 6);
  });
});

function candidate(
  runId: string,
  modelLabel: string,
  quantLabel: string | null,
  vramFootprintGb: number | null,
  point: number,
  lo: number,
  hi: number,
  tokS: number | null,
  kind: "community" | "anchor" = "community",
  lane: string | null = "answer-only",
): RigMatchCandidate {
  return {
    demo: kind === "community",
    family: modelLabel,
    kind,
    lane,
    modelLabel,
    modelSlug: modelLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    nItems: 252,
    nRuns: 1,
    quantLabel,
    runId,
    score: { point, lo, hi },
    tokS,
    vramFootprintGb,
  };
}

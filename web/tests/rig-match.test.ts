import { describe, expect, it } from "vitest";
import {
  VRAM_TIERS,
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
  candidate("llama-q3", "Llama-3.3 70B", "Q3_K_M", 20.2, 69, 66, 72, 18),
  candidate("anchor", "GPT-5.5", null, null, 94, 93, 95, null, "anchor", "api-uncapped"),
] as const satisfies readonly RigMatchCandidate[];

describe("rig-match finder logic", () => {
  it("exposes expanded VRAM tiers through 512 GB while keeping 24 GB available", () => {
    // Given the Phase-3 finder tier contract.
    const expectedTiers = [8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512] as const;

    // When the finder imports its tier options.
    const tiers = VRAM_TIERS;

    // Then the dropdown can cover consumer GPUs through very large local rigs.
    expect(tiers).toEqual(expectedTiers);
    expect(tiers).toContain(24);
  });

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

  it("excludes rows that only fit by weight before 8K context headroom is reserved", () => {
    // Given a large demo quant whose weights alone sit below the selected card size.
    const candidates = [
      candidate("llama-405b-q3", "Llama-3.1-405B", "Q3_K_M", 180, 75, 72, 78, 15),
      candidate("fits-with-headroom", "Smaller 405B", "Q4_K_M", 150, 70, 68, 72, 18),
    ] as const satisfies readonly RigMatchCandidate[];

    // When matches are ranked for a 192 GB rig.
    const matches = rankRigMatches({
      anchors: ANCHORS,
      candidates,
      lane: "answer-only",
      quant: "any",
      vramGb: 192,
    });

    // Then the 180 GB row is excluded because KV cache and runtime overhead push it over budget.
    expect(matches.map((match) => match.runId)).toEqual(["fits-with-headroom"]);
  });

  it("recomputes fit when the selected context length grows", () => {
    // Given a quant that fits 24 GB only at the default 8K context assumption.
    const candidates = [candidate("qwen-q5", "Qwen3 32B", "Q5_K_M", 21.4, 72.6, 70.4, 74.8, 31)] as const;

    // When matches are ranked at 8K and 32K context.
    const matchesAt8k = rankRigMatches({
      anchors: ANCHORS,
      candidates,
      lane: "answer-only",
      quant: "any",
      vramGb: 24,
    });
    const matchesAt32k = rankRigMatches({
      anchors: ANCHORS,
      candidates,
      contextTokens: 32768,
      lane: "answer-only",
      quant: "any",
      vramGb: 24,
    });

    // Then the same weights are treated differently once KV cache grows with context.
    expect(matchesAt8k.map((match) => match.runId)).toEqual(["qwen-q5"]);
    expect(matchesAt32k.map((match) => match.runId)).toEqual([]);
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
    axes: {
      instruction: { point: point + 1, lo, hi, raw_accuracy: 0.8, n: 126, n_errors: 0, n_no_answer: 0 },
      knowledge: { point: point - 1, lo, hi, raw_accuracy: 0.8, n: 126, n_errors: 0, n_no_answer: 0 },
    },
    demo: kind === "community",
    family: modelLabel,
    kind,
    lane,
    tier: "standard",
    modelLabel,
    modelSlug: modelLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    nItems: 252,
    nRuns: 1,
    quantLabel,
    runId,
    score: { point, lo, hi },
    scoreStatus: "measured",
    tokS,
    latencySMedian: null,
    wallTimeSeconds: null,
    vramFootprintGb,
    vramRequiredGb8k: null,
  };
}

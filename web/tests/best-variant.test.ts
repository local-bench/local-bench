import { describe, expect, it } from "vitest";
import { selectBestVariantPoints } from "../lib/best-variant";
import type { RigMatchCandidate } from "../lib/rig-match";

function candidate(overrides: Partial<RigMatchCandidate> = {}): RigMatchCandidate {
  return {
    axes: {},
    demo: false,
    family: "fam",
    kind: "community",
    lane: "capped-thinking",
    modelLabel: "M",
    modelSlug: "m",
    nItems: 100,
    nRuns: 1,
    quantLabel: "Q4_K_M",
    runId: "r",
    score: { point: 50, lo: 45, hi: 55 },
    scoreStatus: "measured",
    tier: "standard",
    tokS: 30,
    vramFootprintGb: 8,
    vramRequiredGb8k: 10,
    latencySMedian: 13.2,
    wallTimeSeconds: 4200,
    ...overrides,
  };
}

describe("selectBestVariantPoints", () => {
  it("keeps only the best-scoring run per model", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "a", runId: "a-q4", score: { point: 60, lo: 55, hi: 65 }, quantLabel: "Q4_K_M" }),
      candidate({ modelSlug: "a", runId: "a-q8", score: { point: 58, lo: 53, hi: 63 }, quantLabel: "Q8_0" }),
    ]);
    expect(points).toHaveLength(1);
    expect(points[0]?.runId).toBe("a-q4");
  });

  it("excludes demo, anchor, unmeasured, and unranked (quick-tier) candidates", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "demo", demo: true }),
      candidate({ modelSlug: "anchor", kind: "anchor" }),
      candidate({ modelSlug: "missing", scoreStatus: "missing", score: null }),
      candidate({ modelSlug: "quick", tier: "quick" }),
      candidate({ modelSlug: "ok", runId: "ok-r" }),
    ]);
    expect(points.map((point) => point.modelSlug)).toEqual(["ok"]);
  });

  it("marks the efficiency frontier (non-dominated points)", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "small", runId: "s", score: { point: 40, lo: 35, hi: 45 }, vramRequiredGb8k: 6 }),
      candidate({ modelSlug: "big", runId: "b", score: { point: 70, lo: 65, hi: 75 }, vramRequiredGb8k: 40 }),
      candidate({ modelSlug: "dominated", runId: "d", score: { point: 30, lo: 25, hi: 35 }, vramRequiredGb8k: 40 }),
    ]);
    const frontier = points
      .filter((point) => point.isFrontier)
      .map((point) => point.modelSlug)
      .sort();
    expect(frontier).toEqual(["big", "small"]);
  });

  it("carries per-answer latency onto the best-variant point", () => {
    const points = selectBestVariantPoints([candidate()]);
    expect(points).toHaveLength(1);
    expect(points[0]!.latencySMedian).toBe(13.2);
  });

  it("carries total bench time onto the best-variant point", () => {
    const points = selectBestVariantPoints([candidate()]);
    expect(points).toHaveLength(1);
    expect(points[0]!.wallTimeSeconds).toBe(4200);
  });
});

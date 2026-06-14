import { describe, expect, it } from "vitest";
import { getQuantDecisionRows, type QuantDecisionInputModel, type QuantDecisionInputRun } from "../lib/quant-decision";

describe("quant decision matrix logic", () => {
  it("marks the lowest-VRAM quant retaining at least 95 percent of FP16 quality as the sweet spot", () => {
    // Given a quant ladder with an FP16 baseline and nearby Q5/Q4 tradeoffs.
    const model = modelWithRuns([
      run("FP16", 64, 75, 12),
      run("Q5_K_M", 21.4, 72.6, 31),
      run("Q4_K_M", 19, 71.2, 42),
    ]);

    // When decision rows are built for the default 8K context assumption.
    const rows = getQuantDecisionRows(model, 8192);

    // Then Q5 is the lowest-VRAM row that keeps at least 95 percent of FP16 quality.
    const q5 = rows.rows.find((row) => row.quantLabel === "Q5_K_M");
    const q4 = rows.rows.find((row) => row.quantLabel === "Q4_K_M");
    expect(q5?.isSweetSpot).toBe(true);
    expect(q5?.fitTierGb).toBe(24);
    expect(q5?.vramEstimate?.effectiveRequiredGb).toBeGreaterThan(21.4);
    expect(q4?.isSweetSpot).toBe(false);
  });

  it("reports coverage gaps when a quant or the FP16 baseline is missing", () => {
    // Given a model page with only one measured quant and no FP16 baseline.
    const model = modelWithRuns([run("Q4_K_M", 19, 71.2, 42)]);

    // When decision rows are built.
    const rows = getQuantDecisionRows(model, 8192);

    // Then the caller can render coverage cards instead of a broken hero.
    expect(rows.hasBaseline).toBe(false);
    expect(rows.missingQuantLabels).toEqual(["FP16", "Q8_0", "Q5_K_M", "Q3_K_M"]);
    expect(rows.rows.find((row) => row.quantLabel === "FP16")?.run).toBeNull();
  });
});

function modelWithRuns(runs: readonly QuantDecisionInputRun[]): QuantDecisionInputModel {
  return {
    demo: true,
    family: "Qwen3",
    kind: "community",
    model_label: "Qwen3 32B",
    runs,
    slug: "qwen3-32b",
  };
}

function run(quantLabel: string, vramFootprintGb: number, point: number, tokS: number): QuantDecisionInputRun {
  return {
    composite: { hi: point + 2, lo: point - 2, point },
    demo: true,
    quant_label: quantLabel,
    run_id: `run-${quantLabel.toLowerCase()}`,
    tok_s: tokS,
    vram_footprint_gb: vramFootprintGb,
  };
}

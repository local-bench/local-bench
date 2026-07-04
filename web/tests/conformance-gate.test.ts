import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { BestVariantTable } from "../components/best-variant-table";
import { IndexModelSchema, ModelRunSchema, type ConformanceGate } from "../lib/schemas";
import type { BestVariantPoint } from "../lib/best-variant";

const RED_GATE = gate("red", 90);
const GREEN_GATE = gate("green", 70);

describe("conformance gate data", () => {
  it("parses optional gates on index rows and model runs", () => {
    // Given: board-provided Tool calling gate sidecars are present on both web data row types.
    const indexRow = IndexModelSchema.parse({
      axes: {},
      best_run_id: "model-a__run",
      composite: { point: 80, lo: 75, hi: 85 },
      conformance_gates: { tc_json_v1: RED_GATE },
      demo: false,
      est_cost_usd: null,
      family: "Fixture",
      kind: "community",
      lane: "capped-thinking",
      model_label: "Model A",
      n_runs: 1,
      ranked: true,
      replicated: false,
      runtime: { name: "llama.cpp", version: "b1234" },
      score_status: "measured",
      slug: "model-a",
      tier: "standard",
      tokens_to_answer_median: 100,
    });
    const runRow = ModelRunSchema.parse({
      axes: {},
      composite: { point: 80, lo: 75, hi: 85 },
      conformance_gates: { tc_json_v1: GREEN_GATE },
      est_cost_usd: null,
      hardware: { cpu: null, gpu: null, os: null, ram_gb: null },
      lane: "capped-thinking",
      n_errors: 0,
      n_items: 100,
      quant_label: "Q4_K_M",
      run_id: "model-a__run",
      runtime: { ctx_len_configured: null, kv_cache_quant: null, name: null, parallel_slots: null, version: null },
      score_status: "measured",
      tier: "standard",
      tok_s: 20,
      tokens_to_answer_median: 100,
      vram_footprint_gb: 16,
    });

    // Then: the gate survives parsing with its board-provided band.
    expect(indexRow.conformance_gates?.tc_json_v1?.band).toBe("red");
    expect(indexRow.runtime?.name).toBe("llama.cpp");
    expect(IndexModelSchema.parse({ ...indexRow, runtime: undefined }).runtime).toBeUndefined();
    expect(runRow.conformance_gates?.tc_json_v1?.band).toBe("green");
  });

  it("does not let gate band change landing table rank order", () => {
    // Given: the lower-scoring model has a green gate and the higher-scoring model has a red gate.
    const html = renderToStaticMarkup(
      createElement(BestVariantTable, {
        points: [
          point("lower-green", "Lower Green", 70, GREEN_GATE),
          point("higher-red", "Higher Red", 90, RED_GATE),
        ],
      }),
    );

    // When: the landing table is rendered.
    const higherIndex = html.indexOf("Higher Red");
    const lowerIndex = html.indexOf("Lower Green");

    // Then: score still controls rank order; gate band is only presentation.
    expect(higherIndex).toBeGreaterThan(-1);
    expect(lowerIndex).toBeGreaterThan(-1);
    expect(higherIndex).toBeLessThan(lowerIndex);
  });
});

function gate(band: ConformanceGate["band"], point: number): ConformanceGate {
  return {
    id: "tc_json_v1",
    label: "Tool-calling",
    band,
    pass_rate: { point, lo: point - 4, hi: point + 4 },
    invalid_json_rate: band === "red" ? 18 : 2,
    n_items: 330,
    threshold_version: "tc_json_v1",
    band_reasons: band === "red" ? ["invalid_json>15"] : [],
  };
}

function point(runId: string, modelLabel: string, score: number, tcJsonGate: ConformanceGate): BestVariantPoint {
  return {
    axes: {},
    conformanceGates: { tc_json_v1: tcJsonGate },
    effectiveVramGb: 16,
    family: "Fixture",
    isFrontier: false,
    modelLabel,
    modelSlug: runId,
    nRuns: 1,
    quantLabel: "Q4_K_M",
    runId,
    score: { point: score, lo: score - 2, hi: score + 2 },
    tokS: 20,
    latencySMedian: 10,
    wallTimeSeconds: 100,
  };
}

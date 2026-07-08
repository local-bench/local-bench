import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelVariantBoard } from "../components/model-variant-board";
import type { ModelData, ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "../lib/data";
import { ModelSlugSchema, RunIdSchema, type AxisScore } from "../lib/schemas";

describe("model variant board runtime display", () => {
  it("shows the serving runtime for each measured variant", () => {
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: fixtureModel() }));

    expect(html).toContain("Runtime");
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
    expect(html).not.toContain("decode tok/s");
  });

  it("omits legacy-lane runs from the model page entirely", () => {
    const base = fixtureModel();
    const current = base.runs[0];
    if (current === undefined) {
      throw new Error("fixture missing run");
    }
    const legacy: ModelData["runs"][number] = {
      ...current,
      composite: null,
      diagnostic_composite: { hi: 62, lo: 58, point: 60 },
      lane: "capped-thinking",
      quant_label: "Q8_0",
      ranked: false,
      run_id: RunIdSchema.parse("legacy-run"),
    };
    const html = renderToStaticMarkup(
      createElement(ModelVariantBoard, { model: { ...base, runs: [current, legacy] } }),
    );

    // Retired-lane runs are omitted (owner call 2026-07-07): no diagnostics table, no
    // receipt link, no legacy composite anywhere on the page.
    expect(html).not.toContain("Previous-index diagnostics");
    expect(html).not.toContain("capped-thinking");
    expect(html).not.toContain('href="/run/legacy-run"');
    expect(html).not.toContain("60.0");
    // The main table still ranks the current-index run.
    expect(html).toContain("85.0");
  });

  it("shows a benchmark CTA when every measured run is legacy-lane", () => {
    const base = fixtureModel();
    const current = base.runs[0];
    if (current === undefined) {
      throw new Error("fixture missing run");
    }
    const legacyOnly: ModelData = {
      ...base,
      runs: [{ ...current, lane: "capped-thinking", ranked: false }],
    };
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: legacyOnly }));

    expect(html).toContain("No current-index measurements yet");
    expect(html).not.toContain("Previous-index diagnostics");
  });

  it("shows the compact decode tok/s column only when a run has serving perf", () => {
    const base = fixtureModel();
    const run = base.runs[0];
    if (run === undefined) {
      throw new Error("fixture missing run");
    }
    const model: ModelData = {
      ...base,
      runs: [
        {
          ...run,
          perf: {
            decode_tps: 42.4,
            per_bench: {},
            prefill_tps: 812.3,
            prompt_ms_median: 122,
            prompt_ms_p95: 250,
            predicted_ms_median: 3_100,
            predicted_ms_p95: 4_400,
            timings_source: "llama.cpp",
            timings_coverage: 0.91,
            ttft_proxy_ms_median: 125,
          },
        },
      ],
    };
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));

    expect(html).toContain("decode tok/s");
    expect(html).toContain("42.4");
  });

  it("renders family rows without letting them become this model's sweet spot", () => {
    const base = fixtureModel();
    const ownRun = base.runs[0];
    if (ownRun === undefined) {
      throw new Error("fixture missing run");
    }
    const familyRun: ModelDataWithConfiguredAxes["runs"][number] = {
      ...ownRun,
      axes: configuredAxes(),
      composite: { hi: 99, lo: 97, point: 98 },
      file_gb: 1.1,
      quant_label: "Q2_K",
      run_id: RunIdSchema.parse("qwopus-family-run"),
      vram_footprint_gb: 2,
    };
    const family: ModelFamilyScatterModel = {
      relation: "family-finetune",
      model: {
        ...base,
        model_label: "Qwopus 3.6 27B v2 MTP",
        runs: [familyRun],
        slug: ModelSlugSchema.parse("qwopus3-6-27b-v2-mtp"),
      },
    };

    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { familyModels: [family], model: base }));
    const familyStart = html.indexOf("fine-tune");
    const familyEnd = html.indexOf("fixture-run", familyStart);
    if (familyStart === -1 || familyEnd === -1) {
      throw new Error("Expected family row before own fixture row");
    }
    const familyRow = html.slice(familyStart, familyEnd);

    expect(familyRow).toContain("fine-tune");
    expect(familyRow).toContain('href="/model/qwopus3-6-27b-v2-mtp"');
    expect(familyRow).toContain('href="/run/qwopus-family-run"');
    expect(familyRow).not.toContain("sweet spot");
  });
});

function fixtureModel(): ModelData {
  return {
    demo: false,
    family: "Fixture",
    kind: "community",
    model_kind: "base",
    model_label: "Fixture Model",
    runs: [
      {
        axes: {},
        composite: { hi: 90, lo: 80, point: 85 },
        demo: false,
        est_cost_usd: null,
        file_gb: null,
        hardware: { cpu: null, gpu: null, os: null, ram_gb: null },
        lane: "bounded-final-v2",
        n_errors: 0,
        n_items: 10,
        quant_label: "Q4_K_M",
        ranked: true,
        run_id: RunIdSchema.parse("fixture-run"),
        runtime: {
          ctx_len_configured: 8192,
          kv_cache_quant: "q8_0",
          name: "llama.cpp",
          parallel_slots: 1,
          version: "b1234",
        },
        score_status: "measured",
        tier: "standard",
        tok_s: 20,
        tokens_to_answer_median: 128,
        vram_footprint_gb: 12,
      },
    ],
    slug: ModelSlugSchema.parse("fixture-model"),
  };
}

function configuredAxes(): ModelDataWithConfiguredAxes["runs"][number]["axes"] {
  const emptyAxis: AxisScore = { hi: 0, lo: 0, n: 0, n_errors: 0, n_no_answer: 0, point: 0, raw_accuracy: 0 };
  return {
    agentic: emptyAxis,
    coding: emptyAxis,
    instruction: emptyAxis,
    knowledge: emptyAxis,
    math: emptyAxis,
    tool_calling: emptyAxis,
  };
}

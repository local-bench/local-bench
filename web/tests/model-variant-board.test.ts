import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelVariantBoard } from "../components/model-variant-board";
import { getCompareConfigs } from "../lib/compare";
import type { ModelData, ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "../lib/data";
import { resolveRunArtifactMetrics } from "../lib/model-run-metrics";
import { ModelSlugSchema, RunIdSchema, type AxisScore } from "../lib/schemas";

describe("model variant board runtime display", () => {
  it("shows the serving runtime for each measured variant", () => {
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: fixtureModel() }));

    expect(html).toContain("Runtime");
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
    expect(html).toContain("Swipe horizontally for all variant metrics");
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

  it("shows the prefill and decode tok/s columns only when a run has serving perf", () => {
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

    expect(html).toContain("Prefill tok/s");
    expect(html).toContain("812.3");
    expect(html).toContain("Decode tok/s");
    expect(html).toContain("42.4");
    expect(html).toContain("Overall tok/s");
    expect(html).toContain("File size");
    expect(html).not.toContain("Footprint");
  });

  it("discloses a runtime-footprint VRAM fallback without using it as file size", () => {
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: fixtureModel() }));
    const cells = firstRankedRowCells(html);
    const vramCell = cells[9] ?? "";
    const fileSizeCell = cells[cells.length - 3] ?? "";

    expect(vramCell).toContain('title="runtime footprint (8k figure unavailable)"');
    expect(vramCell).toContain("12 GB");
    expect(vramCell).toContain("footprint");
    expect(fileSizeCell).toContain("—");
    expect(fileSizeCell).not.toContain("12 GB");
    expect(fileSizeCell).not.toContain("n/a");
  });

  it("renders direct VRAM and file-size values without fallback disclosure", () => {
    const base = fixtureModel();
    const run = base.runs[0];
    if (run === undefined) throw new Error("fixture missing run");
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, {
      model: { ...base, runs: [{ ...run, file_gb: 6.5, vram_required_gb_8k: 10 }] },
    }));
    const cells = firstRankedRowCells(html);
    const vramCell = cells[9] ?? "";
    const fileSizeCell = cells[cells.length - 3] ?? "";

    expect(vramCell).toContain("10 GB");
    expect(vramCell).not.toContain("runtime footprint");
    expect(fileSizeCell).toContain("6.5 GB");
  });

  it("joins measured rows to same-quant catalog metrics across model and compare surfaces", () => {
    // Given a Gemma-31B-shaped measured row whose weights-only footprint is not its 8K requirement,
    // plus the same artifact's catalog sibling carrying the display facts.
    const base = fixtureModel();
    const measured = base.runs[0];
    if (measured === undefined) throw new Error("fixture missing run");
    const catalogSibling: ModelData["runs"][number] = {
      ...measured,
      composite: null,
      file_gb: 18.3,
      lane: "capped-thinking",
      ranked: false,
      run_id: RunIdSchema.parse("gemma31-catalog-sibling"),
      score_status: "missing",
      vram_footprint_gb: 18.32,
      vram_required_gb_8k: 20.9,
    };
    const currentMeasured: ModelData["runs"][number] = {
      ...measured,
      file_gb: null,
      quant_label: "Q4_K_M",
      run_id: RunIdSchema.parse("gemma31-measured"),
      vram_footprint_gb: 18.323731456,
      vram_required_gb_8k: null,
    };
    const model = { ...base, runs: [catalogSibling, currentMeasured] };

    // When the model table and compare config resolve the measured artifact.
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model }));
    const cells = firstRankedRowCells(html);
    const source = resolveRunArtifactMetrics(currentMeasured, model.runs);
    const compare = getCompareConfigs([model]).find((config) => config.runId === "gemma31-measured");

    // Then both surfaces use the catalog 20.9 GB estimate and the file cell never uses footprint.
    expect(cells[9]).toContain("20.9 GB");
    expect(cells[cells.length - 3]).toContain("18.3 GB");
    expect(cells[9]).not.toContain("footprint");
    expect(source).toMatchObject({ fileGb: 18.3, vramRequiredGb8k: 20.9 });
    expect(compare?.vramEstimate?.effectiveRequiredGb).toBe(source.vramRequiredGb8k);
  });

  it("withholds the Index for a partial diagnostic row", () => {
    // Given a current-lane partial row with a legacy composite that cannot be recomputed from its visible axes.
    const base = fixtureModel();
    const measured = base.runs[0];
    if (measured === undefined) throw new Error("fixture missing run");
    const partial: ModelData["runs"][number] = {
      ...measured,
      axes: { instruction: configuredAxes().instruction },
      composite: { hi: 18.05, lo: 16.5, point: 17.34 },
      quant_label: "QAT Q2_K_XL",
      ranked: false,
      run_id: RunIdSchema.parse("partial-diagnostic"),
    };

    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: { ...base, runs: [partial] } }));
    const cells = rowCellsContaining(html, "partial-diagnostic");

    // Then the Index cell is deliberately blanked while the diagnostic qualifier stays visible.
    expect(cells[2]).toContain("—");
    expect(cells[2]).toContain("diagnostic partial — no comparable Index");
    expect(cells[2]).not.toContain("17.3");
  });

  it("labels ranks as scoped to this family", () => {
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: fixtureModel() }));

    expect(html).toContain("Rank (this family)");
    expect(html).toContain("Ranks are within this family&#x27;s variants");
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
    expect(familyRow).toContain('href="/model/qwopus3-6-27b-v2-mtp/"');
    expect(familyRow).toContain('href="/run/qwopus-family-run/"');
    expect(familyRow).not.toContain("sweet spot");
  });

  it("includes a complete community run in the family ranking", () => {
    const base = fixtureModel();
    const trusted = base.runs[0];
    if (trusted === undefined) throw new Error("fixture missing run");
    const adversary: ModelData["runs"][number] = {
      ...trusted,
      composite: { hi: 100, lo: 100, point: 100 },
      origin: "community",
      quant_label: "Q2_K",
      run_id: RunIdSchema.parse("community-adversary"),
      runtime: { ...trusted.runtime, version: "adversary-runtime" },
      trust_label: "community_self_submitted",
    };
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: { ...base, runs: [trusted, adversary] } }));
    expect(html).toContain("fixture-run");
    expect(html).toContain(">best<");
    expect(html).toContain("community-adversary");
    expect(html).toContain("adversary-runtim...");
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
        axes: configuredAxes(),
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
        origin: "project_anchor",
        trust_label: "project_anchor",
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
  const emptyAxis: AxisScore = { hi: 0, lo: 0, n: 1, n_errors: 0, n_no_answer: 0, point: 0, raw_accuracy: 0 };
  return {
    agentic: emptyAxis,
    coding: emptyAxis,
    instruction: emptyAxis,
    knowledge: emptyAxis,
    math: emptyAxis,
    tool_calling: emptyAxis,
  };
}

function firstRankedRowCells(html: string): readonly string[] {
  const body = html.match(/<tbody>([\s\S]*?)<\/tbody>/u)?.[1] ?? "";
  const row = body.match(/<tr[\s\S]*?<\/tr>/u)?.[0] ?? "";
  return [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((match) => match[1] ?? "");
}

function rowCellsContaining(html: string, text: string): readonly string[] {
  const row = [...html.matchAll(/<tr[\s\S]*?<\/tr>/gu)]
    .map((match) => match[0])
    .find((candidate) => candidate.includes(text)) ?? "";
  return [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((match) => match[1] ?? "");
}

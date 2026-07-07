import { describe, expect, it } from "vitest";
import { CatalogSchema, IndexModelSchema, ModelDataSchema } from "../lib/schemas";

const catalogModel = {
  id: "Qwen/Qwen3.6-27B",
  slug: "qwen3-6-27b",
  display_name: "Qwen3.6 27B",
  family: "Qwen3.6",
  org: "Qwen",
  params_b: 27,
  reasoning_capable: true,
  license: "apache-2.0",
  gguf_repo: "unsloth/Qwen3.6-27B-MTP-GGUF",
  quants: [{ label: "Q4_K_M", bpw: 4.85, file_gb: 17.1, vram_gb_8k: 19.5 }],
};

describe("CatalogSchema", () => {
  it("parses old catalogs and defaults model_kind to base", () => {
    const parsed = CatalogSchema.parse([catalogModel]);

    expect(Array.isArray(parsed) ? parsed[0]?.model_kind : null).toBe("base");
  });

  it("parses promoted derivative model_kind values", () => {
    const parsed = CatalogSchema.parse({
      popularity_as_of: "2026-07-05",
      models: [
        {
          ...catalogModel,
          id: "Jackrong/Qwopus3.6-27B-v2-MTP",
          slug: "qwopus3-6-27b-v2-mtp",
          display_name: "Qwopus 3.6 27B v2 MTP",
          base_model: "Qwen/Qwen3.6-27B",
          model_kind: "finetune",
        },
      ],
    });

    expect(Array.isArray(parsed) ? null : parsed.models[0]?.model_kind).toBe("finetune");
  });
});

describe("diagnostic composite schemas", () => {
  it("parses diagnostic_composite on legacy index rows while standard composite is null", () => {
    // Given a retired-lane row with its score moved out of the standard composite field.
    const diagnosticScore = { point: 62.3, lo: 60.1, hi: 64.2 };

    // When the public index schema parses the row.
    const parsed = IndexModelSchema.parse({
      axes: {},
      best_run_id: "legacy-run",
      composite: null,
      diagnostic_composite: diagnosticScore,
      est_cost_usd: null,
      family: "Fixture",
      kind: "community",
      lane: "capped-thinking",
      model_label: "Fixture Legacy",
      n_runs: 1,
      ranked: false,
      replicated: false,
      score_status: "measured",
      slug: "fixture-legacy",
      tier: "standard",
      tokens_to_answer_median: 128,
    });

    // Then the diagnostic score remains available under its explicit field only.
    expect(parsed).toMatchObject({
      composite: null,
      diagnostic_composite: diagnosticScore,
    });
  });

  it("parses diagnostic_composite on model diagnostic rows while standard composite is null", () => {
    // Given a model page run row for an intentionally visible retired-lane diagnostic.
    const diagnosticScore = { point: 52.9, lo: 47.7, hi: 58.1 };

    // When the model schema parses the row.
    const parsed = ModelDataSchema.parse({
      demo: false,
      family: "Fixture",
      kind: "community",
      model_kind: "base",
      model_label: "Fixture Model",
      runs: [
        {
          axes: {},
          composite: null,
          diagnostic_composite: diagnosticScore,
          demo: false,
          est_cost_usd: null,
          file_gb: null,
          hardware: { cpu: null, gpu: null, os: null, ram_gb: null },
          lane: "capped-thinking",
          n_errors: 0,
          n_items: 10,
          quant_label: "Q8_0",
          ranked: false,
          run_id: "legacy-run",
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
      slug: "fixture-model",
    });

    // Then diagnostic model rows can still render the retired-lane score intentionally.
    expect(parsed.runs[0]).toMatchObject({
      composite: null,
      diagnostic_composite: diagnosticScore,
    });
  });
});

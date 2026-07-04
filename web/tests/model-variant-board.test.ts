import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelVariantBoard } from "../components/model-variant-board";
import type { ModelData } from "../lib/data";
import { ModelSlugSchema, RunIdSchema } from "../lib/schemas";

describe("model variant board runtime display", () => {
  it("shows the serving runtime for each measured variant", () => {
    const html = renderToStaticMarkup(createElement(ModelVariantBoard, { model: fixtureModel() }));

    expect(html).toContain("Runtime");
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
  });
});

function fixtureModel(): ModelData {
  return {
    demo: false,
    family: "Fixture",
    kind: "community",
    model_label: "Fixture Model",
    runs: [
      {
        axes: {},
        composite: { hi: 90, lo: 80, point: 85 },
        demo: false,
        est_cost_usd: null,
        file_gb: null,
        hardware: { cpu: null, gpu: null, os: null, ram_gb: null },
        lane: "capped-thinking",
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

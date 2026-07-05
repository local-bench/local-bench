import { describe, expect, it } from "vitest";
import { CatalogSchema } from "../lib/schemas";

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

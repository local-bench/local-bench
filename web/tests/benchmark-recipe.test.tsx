import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BenchmarkRecipe, copyableCommand } from "../components/benchmark-recipe";
import type { BenchmarkRecipe as Recipe, OnrampCatalogModel } from "../lib/onramp";

const baseModel: OnrampCatalogModel = {
  id: "Qwen/Qwen3-8B",
  slug: "qwen3-8b",
  displayName: "Qwen3 8B",
  family: "Qwen3",
  org: "Qwen",
  paramsB: 8.2,
  reasoningCapable: true,
  license: "apache-2.0",
  ggufRepo: "MaziyarPanahi/Qwen3-8B-GGUF",
  downloads: 11_000_000,
  likes: 420,
  trending: 31,
  modelKind: "base",
  baseModelId: null,
  baseModelSlug: null,
  baseModelDisplayName: null,
  quants: [{ label: "Q4_K_M", vramGb8k: 6, fileGb: 5, bpw: 4.8 }],
};

function recipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    setupCommand:
      'pip install "local-bench-ai[hf]==0.2.3"\nlocalbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms\nlocalbench cache-tokenizer Qwen/Qwen3-8B',
    serveCommand:
      "llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --ctx-size 32768 --parallel 1 --alias MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080",
    serveNote: null,
    benchCommand:
      "localbench run \\\n  --endpoint http://localhost:8080/v1 \\\n  --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M \\\n  --hf-model-id Qwen/Qwen3-8B \\\n  --ctx-len-configured 32768 \\\n  --lane bounded-final-v2 \\\n  --profile auto \\\n  --tier standard \\\n  --publishable \\\n  --sampler-seed 1234 \\\n  --out runs/qwen3-8b-q4-k-m.json",
    submitCommand: "localbench submit run --run runs/qwen3-8b-q4-k-m.json",
    lane: "bounded-final-v2",
    servedModelName: "MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M",
    ggufRepo: "MaziyarPanahi/Qwen3-8B-GGUF",
    identityMode: "full",
    model: baseModel,
    ...overrides,
  };
}

describe("BenchmarkRecipe", () => {
  it("shows the full identity badge, gated repo note, cost warning, and single-line copy caption", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe() }));

    expect(html).toContain("Identity: full");
    expect(html).toContain("HF tokenizer/template cached");
    expect(html).toContain("Gated repo");
    expect(html).toContain("hf auth login");
    expect(html).toContain("HF_TOKEN");
    expect(html).toContain("This is a full ranked run");
    expect(html).toContain("Preflight fails fast");
    expect(html).toContain("copies as one line");
  });

  it("shows a loud basic identity badge when tokenizer provenance is absent", () => {
    const html = renderToStaticMarkup(createElement(BenchmarkRecipe, { recipe: recipe({ identityMode: "basic" }) }));

    expect(html).toContain("Identity: basic");
    expect(html).toContain("tokenizer/chat-template digests will be null");
    expect(html).toContain("Add the model");
    expect(html).toContain("exact non-GGUF HF repo");
  });

  it("copies multi-line command blocks as one shell line", () => {
    expect(
      copyableCommand(
        "localbench run \\\n  --endpoint http://localhost:8080/v1 \\\n  --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M",
      ),
    ).toBe("localbench run --endpoint http://localhost:8080/v1 --model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
  });
});

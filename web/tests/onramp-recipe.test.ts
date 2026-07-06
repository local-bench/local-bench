import { describe, expect, it } from "vitest";
import { RUNTIME_PROFILES, buildRecipe, type OnrampCatalogModel, type OnrampCatalogQuant, type RuntimeId, type RuntimeProfile } from "../lib/onramp";

function model(overrides: Partial<OnrampCatalogModel> = {}): OnrampCatalogModel {
  return {
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
    quants: [
      { label: "Q8_0", vramGb8k: 10.1, fileGb: 8.7, bpw: 8.5 },
      { label: "Q6_K", vramGb8k: 8.2, fileGb: 6.8, bpw: 6.6 },
      { label: "Q4_K_M", vramGb8k: 6.0, fileGb: 5.0, bpw: 4.8 },
    ],
    ...overrides,
  };
}

function runtimeProfile(id: RuntimeId): RuntimeProfile {
  const profile = RUNTIME_PROFILES.find((candidate) => candidate.id === id);
  if (profile === undefined) {
    throw new Error(`Missing runtime profile: ${id}`);
  }
  return profile;
}

function quantAt(entry: OnrampCatalogModel, index: number): OnrampCatalogQuant {
  const quant = entry.quants[index];
  if (quant === undefined) {
    throw new Error(`Missing quant at index ${index}`);
  }
  return quant;
}

describe("buildRecipe", () => {
  const llamacpp = runtimeProfile("llamacpp");
  const vllm = runtimeProfile("vllm");
  const lmstudio = runtimeProfile("lmstudio");

  it("emits a board-comparable bounded-final recipe for a Qwen model on llama.cpp", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.ggufRepo).toBe("MaziyarPanahi/Qwen3-8B-GGUF");
    expect(recipe.model).toBe(selected);
    expect(recipe.setupCommand).toBe(
      'pip install "local-bench-ai[hf]==0.2.2"\nlocalbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms\nhf download Qwen/Qwen3-8B --include "*.json" --include "*.model" --include "*.jinja" --include "*.txt" --include "*.tiktoken"',
    );
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/qwen3-8b-q4-k-m.json");
    expect(recipe.servedModelName).toBe("MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe(
      "llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --ctx-size 32768 --parallel 1 --alias MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080",
    );
    expect(recipe.identityMode).toBe("full");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8080/v1");
    expect(recipe.benchCommand).toContain("--model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/Qwen3-8B");
    expect(recipe.benchCommand).toContain("--ctx-len-configured 32768");
    expect(recipe.benchCommand).toContain("--lane bounded-final-v2");
    expect(recipe.benchCommand).toContain("--profile auto");
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).toContain("--publishable");
    expect(recipe.benchCommand).toContain("--sampler-seed 1234");
    expect(recipe.benchCommand).toContain("--tier standard");
    expect(recipe.benchCommand).toContain("--out runs/qwen3-8b-q4-k-m.json");
    expect(recipe.benchCommand).not.toContain("--suite-dir");
    expect(recipe.benchCommand).toContain(" \\\n  --endpoint");
  });

  it("emits a basic identity recipe for pasted GGUF repos without an HF identity repo", () => {
    const pasted = model({
      id: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      slug: "deepseek-r1-distill-qwen-7b-gguf",
      displayName: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      ggufRepo: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
      quants: [{ label: "Q4_K_M", vramGb8k: null, fileGb: null, bpw: null }],
    });
    const recipe = buildRecipe({ model: pasted, quant: quantAt(pasted, 0), runtime: llamacpp, hfModelId: null });

    expect(recipe.identityMode).toBe("basic");
    expect(recipe.setupCommand).not.toContain("hf download");
    expect(recipe.benchCommand).not.toContain("--hf-model-id");
    expect(recipe.benchCommand).toContain("--model bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--out runs/deepseek-r1-distill-qwen-7b-gguf-q4-k-m.json");
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/deepseek-r1-distill-qwen-7b-gguf-q4-k-m.json");
  });

  it("emits a full identity recipe for pasted GGUF repos with an exact HF identity repo", () => {
    const pasted = model({
      id: "bartowski/QwQ-32B-GGUF",
      slug: "qwq-32b-gguf",
      displayName: "bartowski/QwQ-32B-GGUF",
      ggufRepo: "bartowski/QwQ-32B-GGUF",
      quants: [{ label: "Q5_K_M", vramGb8k: null, fileGb: null, bpw: null }],
    });
    const recipe = buildRecipe({ model: pasted, quant: quantAt(pasted, 0), runtime: llamacpp, hfModelId: "Qwen/QwQ-32B" });

    expect(recipe.identityMode).toBe("full");
    expect(recipe.setupCommand).toContain('hf download Qwen/QwQ-32B --include "*.json"');
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/QwQ-32B");
    expect(recipe.benchCommand).toContain("--out runs/qwq-32b-gguf-q5-k-m.json");
  });

  it("uses the HF model id as the served name for vLLM and warns about full weights", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000 --generation-config vllm");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8000/v1");
    expect(recipe.serveNote).toContain("full-precision");
    expect(recipe.serveNote).not.toContain("pass --generation-config vllm");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
    expect(recipe.serveNote).toContain("curl http://localhost:1234/v1/models");
  });

  it("gives a non-reasoning model the same ranked bounded-final recipe (profile auto)", () => {
    const selected = model({ reasoningCapable: false });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/qwen3-8b-q4-k-m.json");
    expect(recipe.benchCommand).toContain("--lane bounded-final-v2");
    expect(recipe.benchCommand).toContain("--profile auto");
  });

  it("gives a reasoning model outside Qwen3/Gemma the same ranked bounded-final recipe", () => {
    const selected = model({ family: "Granite 3", org: "IBM" });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.lane).toBe("bounded-final-v2");
    expect(recipe.benchCommand).toContain("--profile auto");
  });

  it("carries fine-tune lineage through the recipe model payload", () => {
    const selected = model({
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      displayName: "Qwopus3.6 27B v2 MTP",
    });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.model.baseModelDisplayName).toBe("Qwen3.6 27B");
    expect(recipe.model.baseModelSlug).toBe("qwen3-6-27b");
  });
});

import { describe, expect, it } from "vitest";
import {
  RUNTIME_PROFILES,
  buildRecipe,
  listOrgs,
  modelsForOrg,
  recommendModels,
  recommendedQuantForVram,
  reasoningActivationFor,
  type OnrampCatalogModel,
} from "../lib/onramp";
import { getOnrampCatalog } from "../lib/data";

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
    quants: [
      { label: "Q8_0", vramGb8k: 10.1, fileGb: 8.7, bpw: 8.5 },
      { label: "Q6_K", vramGb8k: 8.2, fileGb: 6.8, bpw: 6.6 },
      { label: "Q4_K_M", vramGb8k: 6.0, fileGb: 5.0, bpw: 4.8 },
    ],
    ...overrides,
  };
}

describe("reasoningActivationFor", () => {
  it("maps known families with confidence", () => {
    expect(reasoningActivationFor({ family: "Qwen3", org: "Qwen" })).toEqual({ activation: "qwen3", confident: true });
    expect(reasoningActivationFor({ family: "Granite 3", org: "IBM" })).toEqual({ activation: "granite", confident: true });
    expect(reasoningActivationFor({ family: "Nemotron", org: "NVIDIA" })).toEqual({ activation: "nemotron", confident: true });
    expect(reasoningActivationFor({ family: "DeepSeek-R1-Distill", org: "DeepSeek" })).toEqual({ activation: "r1", confident: true });
    expect(reasoningActivationFor({ family: "Gemma 4", org: "Google" })).toEqual({ activation: "gemma4", confident: true });
  });

  it("falls back to qwen3 without confidence for unknown families", () => {
    expect(reasoningActivationFor({ family: "Mystery", org: "Acme" })).toEqual({ activation: "qwen3", confident: false });
  });
});

describe("recommendedQuantForVram", () => {
  it("picks the highest-quality quant that fits the budget", () => {
    expect(recommendedQuantForVram(model(), 12)?.label).toBe("Q8_0");
    expect(recommendedQuantForVram(model(), 9)?.label).toBe("Q6_K");
    expect(recommendedQuantForVram(model(), 7)?.label).toBe("Q4_K_M");
  });

  it("returns null when nothing fits", () => {
    expect(recommendedQuantForVram(model(), 4)).toBeNull();
  });

  it("ignores quants with unknown VRAM", () => {
    const m = model({ quants: [{ label: "Q4_K_M", vramGb8k: null, fileGb: 5, bpw: 4.8 }] });
    expect(recommendedQuantForVram(m, 24)).toBeNull();
  });
});

describe("recommendModels", () => {
  it("returns only reasoning models with a GGUF repo and a fitting quant, ranked by downloads, capped", () => {
    const catalog = [
      model({ slug: "a", downloads: 100 }),
      model({ slug: "b", downloads: 900 }),
      model({ slug: "no-gguf", ggufRepo: null, downloads: 5000 }),
      model({ slug: "not-reasoning", reasoningCapable: false, downloads: 5000 }),
      model({ slug: "too-big", downloads: 5000, quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }] }),
    ];
    const result = recommendModels(catalog, 24, 5);
    expect(result.map((entry) => entry.model.slug)).toEqual(["b", "a"]);
    expect(result.every((entry) => entry.quant.vramGb8k !== null)).toBe(true);
  });

  it("respects the limit", () => {
    const catalog = [model({ slug: "a", downloads: 3 }), model({ slug: "b", downloads: 2 }), model({ slug: "c", downloads: 1 })];
    expect(recommendModels(catalog, 24, 2)).toHaveLength(2);
  });
});

describe("listOrgs / modelsForOrg", () => {
  it("lists unique orgs sorted, and models per org by downloads", () => {
    const catalog = [
      model({ slug: "q1", org: "Qwen", downloads: 1 }),
      model({ slug: "q2", org: "Qwen", downloads: 9 }),
      model({ slug: "g1", org: "Google" }),
    ];
    expect(listOrgs(catalog)).toEqual(["Google", "Qwen"]);
    expect(modelsForOrg(catalog, "Qwen").map((m) => m.slug)).toEqual(["q2", "q1"]);
  });
});

describe("RUNTIME_PROFILES", () => {
  it("exposes three profiles with llama.cpp recommended and no Ollama", () => {
    expect(RUNTIME_PROFILES.map((p) => p.id)).toEqual(["llamacpp", "lmstudio", "vllm"]);
    expect(RUNTIME_PROFILES.map((p) => String(p.id))).not.toContain("ollama");
    expect(RUNTIME_PROFILES.find((p) => p.id === "llamacpp")?.recommended).toBe(true);
    expect(RUNTIME_PROFILES.find((p) => p.id === "llamacpp")?.endpoint).toBe("http://localhost:8080/v1");
    expect(RUNTIME_PROFILES.find((p) => p.id === "vllm")?.endpoint).toBe("http://localhost:8000/v1");
  });
});

describe("buildRecipe", () => {
  const llamacpp = RUNTIME_PROFILES.find((p) => p.id === "llamacpp")!;
  const vllm = RUNTIME_PROFILES.find((p) => p.id === "vllm")!;
  const lmstudio = RUNTIME_PROFILES.find((p) => p.id === "lmstudio")!;

  it("emits a board-comparable capped-thinking recipe for a reasoning model on llama.cpp", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.lane).toBe("capped-thinking");
    expect(recipe.servedModelName).toBe("MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe("llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080");
    expect(recipe.serveNote).toBeNull();
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8080/v1");
    expect(recipe.benchCommand).toContain("--model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/Qwen3-8B");
    expect(recipe.benchCommand).toContain("--lane capped-thinking");
    expect(recipe.benchCommand).toContain("--reasoning-activation qwen3");
    expect(recipe.benchCommand).toContain("--tier standard");
    expect(recipe.benchCommand).toContain("--out my-run.json");
    expect(recipe.benchCommand.includes("\n")).toBe(false);
  });

  it("uses the HF model id as the served name for vLLM", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8000/v1");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
  });

  it("emits answer-only with no reasoning flags for a non-reasoning model", () => {
    const recipe = buildRecipe({ model: model({ reasoningCapable: false }), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.lane).toBe("answer-only");
    expect(recipe.benchCommand).not.toContain("--hf-model-id");
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).toContain("--lane answer-only");
  });

  it("flags low confidence when the family is unknown", () => {
    const recipe = buildRecipe({ model: model({ family: "Mystery", org: "Acme" }), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.activationConfident).toBe(false);
    expect(recipe.activation).toBe("qwen3");
  });
});

describe("getOnrampCatalog", () => {
  it("loads the real catalog and trims it to on-ramp models", async () => {
    const catalog = await getOnrampCatalog();
    expect(catalog.length).toBeGreaterThan(50);
    for (const entry of catalog) {
      expect(entry.id).toBeTruthy();
      expect(entry.slug).toBeTruthy();
      expect(entry.quants.length).toBeGreaterThan(0);
    }
    const qwen = catalog.find((entry) => entry.slug === "qwen3-8b");
    expect(qwen).toBeDefined();
    expect(qwen?.ggufRepo).toBeTruthy();
    expect(qwen?.quants.some((quant) => quant.label === "Q4_K_M")).toBe(true);
  });
});

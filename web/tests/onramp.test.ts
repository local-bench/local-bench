import { describe, expect, it } from "vitest";
import {
  RUNTIME_PROFILES,
  buildRecipe,
  listOrgs,
  modelsForOrg,
  popularModels,
  recommendedQuantForVram,
  rankedActivationFor,
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

describe("rankedActivationFor", () => {
  it("ranks only Qwen3 and Gemma families (the CLI registry's ranked entries)", () => {
    expect(rankedActivationFor({ family: "Qwen3", org: "Qwen" })).toBe("qwen3");
    expect(rankedActivationFor({ family: "Gemma 4", org: "Google" })).toBe("gemma4");
    expect(rankedActivationFor({ family: "Granite 3", org: "IBM" })).toBeNull();
    expect(rankedActivationFor({ family: "Nemotron", org: "NVIDIA" })).toBeNull();
    expect(rankedActivationFor({ family: "DeepSeek-R1-Distill", org: "DeepSeek" })).toBeNull();
    expect(rankedActivationFor({ family: "Mystery", org: "Acme" })).toBeNull();
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

describe("popularModels", () => {
  it("returns only board-rankable (Qwen3/Gemma) models with a GGUF and a fitting quant, ranked by downloads", () => {
    const catalog = [
      model({ slug: "qwen-a", downloads: 100 }),
      model({ slug: "qwen-b", downloads: 900 }),
      model({ slug: "gemma", family: "Gemma 4", org: "Google", downloads: 500 }),
      model({ slug: "granite", family: "Granite", org: "IBM", downloads: 5000 }),
      model({ slug: "no-gguf", ggufRepo: null, downloads: 5000 }),
      model({ slug: "too-big", downloads: 5000, quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }] }),
    ];
    const result = popularModels(catalog, 24, 5);
    expect(result.map((entry) => entry.model.slug)).toEqual(["qwen-b", "gemma", "qwen-a"]);
    expect(result.every((entry) => entry.quant.vramGb8k !== null)).toBe(true);
  });

  it("respects the limit", () => {
    const catalog = [model({ slug: "a", downloads: 3 }), model({ slug: "b", downloads: 2 }), model({ slug: "c", downloads: 1 })];
    expect(popularModels(catalog, 24, 2)).toHaveLength(2);
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

  it("emits a board-comparable capped-thinking recipe for a Qwen model on llama.cpp, pinning suite/v1", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.boardComparable).toBe(true);
    expect(recipe.lane).toBe("capped-thinking");
    expect(recipe.activation).toBe("qwen3");
    expect(recipe.notRankableReason).toBeNull();
    expect(recipe.servedModelName).toBe("MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe("llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8080/v1");
    expect(recipe.benchCommand).toContain("--model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/Qwen3-8B");
    expect(recipe.benchCommand).toContain("--suite-dir suite/v1");
    expect(recipe.benchCommand).toContain("--lane capped-thinking");
    expect(recipe.benchCommand).toContain("--reasoning-activation qwen3");
    expect(recipe.benchCommand).toContain("--tier standard");
    expect(recipe.benchCommand).toContain("--out my-run.json");
    expect(recipe.benchCommand.includes("\n")).toBe(false);
  });

  it("uses the HF model id as the served name for vLLM and warns about full weights", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8000/v1");
    expect(recipe.serveNote).toContain("full-precision");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
  });

  it("marks a non-reasoning model as not board-comparable (answer-only, still suite-pinned)", () => {
    const recipe = buildRecipe({ model: model({ reasoningCapable: false }), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.boardComparable).toBe(false);
    expect(recipe.lane).toBe("answer-only");
    expect(recipe.activation).toBeNull();
    expect(recipe.benchCommand).not.toContain("--hf-model-id");
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).toContain("--lane answer-only");
    expect(recipe.benchCommand).toContain("--suite-dir suite/v1");
    expect(recipe.notRankableReason).toContain("Not a reasoning model");
  });

  it("marks a reasoning model outside Qwen3/Gemma as not board-comparable", () => {
    const recipe = buildRecipe({ model: model({ family: "Granite 3", org: "IBM" }), quant: model().quants[2]!, runtime: llamacpp });
    expect(recipe.boardComparable).toBe(false);
    expect(recipe.lane).toBe("answer-only");
    expect(recipe.activation).toBeNull();
    expect(recipe.notRankableReason).toContain("Qwen3 and Gemma");
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

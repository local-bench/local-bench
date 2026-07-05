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
  type OnrampCatalogQuant,
  type RuntimeId,
  type RuntimeProfile,
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
  it("returns the most-downloaded rankable models near the top of the fitting size range", () => {
    const catalog = [
      model({ slug: "qwen-8b", paramsB: 8.2, downloads: 100 }),
      model({ slug: "qwen-14b", paramsB: 14.8, downloads: 900 }),
      model({ slug: "gemma-12b", family: "Gemma 4", org: "Google", paramsB: 12.2, downloads: 500 }),
      model({ slug: "tiny-download-magnet", paramsB: 0.6, downloads: 50_000_000 }),
      model({ slug: "granite", family: "Granite", org: "IBM", downloads: 5000 }),
      model({ slug: "no-gguf", ggufRepo: null, downloads: 5000 }),
      model({ slug: "too-big", downloads: 5000, quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }] }),
    ];
    const result = popularModels(catalog, 24, 5);
    expect(result.map((entry) => entry.model.slug)).toEqual(["qwen-14b", "gemma-12b", "qwen-8b"]);
    expect(result.every((entry) => entry.quant.vramGb8k !== null)).toBe(true);
  });

  it("falls back to all fitting candidates when size metadata is missing", () => {
    const catalog = [
      model({ slug: "unknown-a", paramsB: null, downloads: 100 }),
      model({ slug: "unknown-b", paramsB: null, downloads: 900 }),
    ];
    expect(popularModels(catalog, 24, 5).map((entry) => entry.model.slug)).toEqual(["unknown-b", "unknown-a"]);
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
  const llamacpp = runtimeProfile("llamacpp");
  const vllm = runtimeProfile("vllm");
  const lmstudio = runtimeProfile("lmstudio");

  it("emits a board-comparable bounded-final recipe for a Qwen model on llama.cpp", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.boardComparable).toBe(true);
    expect(recipe.lane).toBe("bounded-final-v1");
    expect(recipe.activation).toBe("qwen3");
    expect(recipe.notRankableReason).toBeNull();
    expect(recipe.ggufRepo).toBe("MaziyarPanahi/Qwen3-8B-GGUF");
    expect(recipe.setupCommand).toBe(
      'pip install "local-bench-ai[hf]"\nlocalbench fetch-suite --site https://local-bench.ai --suite suite-v1-text-code-agentic-5axis-v1 --accept-suite-terms',
    );
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/my-run.json");
    expect(recipe.servedModelName).toBe("MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe("llama-server -hf MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M --port 8080");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8080/v1");
    expect(recipe.benchCommand).toContain("--model MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/Qwen3-8B");
    expect(recipe.benchCommand).toContain("--lane bounded-final-v1");
    expect(recipe.benchCommand).toContain("--profile auto");
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).toContain("--publishable");
    expect(recipe.benchCommand).toContain("--sampler-seed 1234");
    expect(recipe.benchCommand).toContain("--tier standard");
    expect(recipe.benchCommand).toContain("--out runs/my-run.json");
    expect(recipe.benchCommand).not.toContain("--suite-dir");
    expect(recipe.benchCommand).toContain(" \\\n  --endpoint");
  });

  it("uses the HF model id as the served name for vLLM and warns about full weights", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8000/v1");
    expect(recipe.serveNote).toContain("full-precision");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const selected = model();
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
  });

  it("gives a non-reasoning model the same ranked bounded-final recipe (profile auto)", () => {
    const selected = model({ reasoningCapable: false });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.boardComparable).toBe(true);
    expect(recipe.lane).toBe("bounded-final-v1");
    expect(recipe.submitCommand).toBe("localbench submit run --run runs/my-run.json");
    expect(recipe.benchCommand).toContain("--lane bounded-final-v1");
    expect(recipe.benchCommand).toContain("--profile auto");
    expect(recipe.notRankableReason).toBeNull();
  });

  it("gives a reasoning model outside Qwen3/Gemma the same ranked bounded-final recipe", () => {
    const selected = model({ family: "Granite 3", org: "IBM" });
    const recipe = buildRecipe({ model: selected, quant: quantAt(selected, 2), runtime: llamacpp });
    expect(recipe.boardComparable).toBe(true);
    expect(recipe.lane).toBe("bounded-final-v1");
    expect(recipe.benchCommand).toContain("--profile auto");
    expect(recipe.notRankableReason).toBeNull();
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

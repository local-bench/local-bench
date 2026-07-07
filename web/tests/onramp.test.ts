import { describe, expect, it } from "vitest";
import {
  bestFitForVram,
  browseFamilies,
  listBaseLabs,
  popularModels,
  recommendedQuantForVram,
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
    likes: 420,
    trending: 31,
    modelKind: "base",
    baseModelIds: [],
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
  it("returns the most-downloaded GGUF models near the top of the fitting size range without family gating", () => {
    const catalog = [
      model({ slug: "qwen-8b", paramsB: 8.2, downloads: 100 }),
      model({ slug: "llama-14b", family: "Llama", org: "Meta", paramsB: 14.8, downloads: 900 }),
      model({ slug: "gemma-12b", family: "Gemma 4", org: "Google", paramsB: 12.2, downloads: 500 }),
      model({ slug: "tiny-download-magnet", paramsB: 0.6, downloads: 50_000_000 }),
      model({ slug: "granite", family: "Granite", org: "IBM", downloads: 5000 }),
      model({ slug: "no-gguf", ggufRepo: null, downloads: 5000 }),
      model({ slug: "too-big", downloads: 5000, quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }] }),
    ];
    const result = popularModels(catalog, 24, "downloads", 5);
    expect(result.map((entry) => entry.model.slug)).toEqual(["granite", "llama-14b", "gemma-12b", "qwen-8b"]);
    expect(result.every((entry) => entry.quant.vramGb8k !== null)).toBe(true);
  });

  it("sorts by downloads, trending, or likes after applying the VRAM filter", () => {
    const catalog = [
      model({ slug: "downloads", downloads: 900, trending: 1, likes: 1 }),
      model({ slug: "trending", downloads: 100, trending: 90, likes: 2 }),
      model({ slug: "likes", downloads: 200, trending: 2, likes: 80 }),
      model({
        slug: "too-big-liked",
        downloads: 1,
        trending: 999,
        likes: 999,
        quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }],
      }),
    ];
    expect(popularModels(catalog, 24, "downloads", 3).map((entry) => entry.model.slug)).toEqual([
      "downloads",
      "likes",
      "trending",
    ]);
    expect(popularModels(catalog, 24, "trending", 3).map((entry) => entry.model.slug)).toEqual([
      "trending",
      "likes",
      "downloads",
    ]);
    expect(popularModels(catalog, 24, "likes", 3).map((entry) => entry.model.slug)).toEqual([
      "likes",
      "trending",
      "downloads",
    ]);
  });

  it("falls back to all fitting candidates when size metadata is missing", () => {
    const catalog = [
      model({ slug: "unknown-a", paramsB: null, downloads: 100 }),
      model({ slug: "unknown-b", paramsB: null, downloads: 900 }),
    ];
    expect(popularModels(catalog, 24, "downloads", 5).map((entry) => entry.model.slug)).toEqual(["unknown-b", "unknown-a"]);
  });

  it("respects the limit", () => {
    const catalog = [model({ slug: "a", downloads: 3 }), model({ slug: "b", downloads: 2 }), model({ slug: "c", downloads: 1 })];
    expect(popularModels(catalog, 24, "downloads", 2)).toHaveLength(2);
  });
});

describe("browseFamilies", () => {
  const qwenBase = model({
    id: "Qwen/Qwen3.6-27B",
    slug: "qwen3-6-27b",
    displayName: "Qwen3.6 27B",
    downloads: 10_000,
  });
  const llamaBase = model({
    id: "meta-llama/Llama-3.1-8B",
    slug: "llama-3-1-8b",
    displayName: "Llama 3.1 8B",
    org: "Meta",
    downloads: 8_000,
  });
  const outsideBaseLink = model({
    id: "Qwen/Qwen3-0.6B",
    slug: "qwen3-0-6b",
    displayName: "Qwen3 0.6B",
    baseModelIds: ["Qwen/Qwen3-0.6B-Base"],
    baseModelId: "Qwen/Qwen3-0.6B-Base",
    baseModelSlug: null,
    baseModelDisplayName: "Qwen/Qwen3-0.6B-Base",
    downloads: 500,
  });
  const qwopus = model({
    id: "Jackrong/Qwopus3.6-27B-v2-MTP",
    slug: "qwopus3-6-27b-v2-mtp",
    displayName: "Qwopus3.6 27B v2 MTP",
    org: "Jackrong",
    baseModelIds: ["Qwen/Qwen3.6-27B"],
    baseModelId: "Qwen/Qwen3.6-27B",
    baseModelSlug: "qwen3-6-27b",
    baseModelDisplayName: "Qwen3.6 27B",
    modelKind: "finetune",
    downloads: 2_400,
    likes: 55,
  });
  const officialVariant = model({
    id: "Qwen/Qwen3.6-27B-Thinking",
    slug: "qwen3-6-27b-thinking",
    displayName: "Qwen3.6 27B Thinking",
    org: "Qwen",
    baseModelIds: ["Qwen/Qwen3.6-27B"],
    baseModelId: "Qwen/Qwen3.6-27B",
    baseModelSlug: "qwen3-6-27b",
    baseModelDisplayName: "Qwen3.6 27B",
    modelKind: "finetune",
    downloads: 1_200,
  });
  const merge = model({
    id: "MergeLab/Qwen-Llama-Merge",
    slug: "qwen-llama-merge",
    displayName: "Qwen Llama Merge",
    org: "MergeLab",
    baseModelIds: ["Qwen/Qwen3.6-27B", "meta-llama/Llama-3.1-8B"],
    baseModelId: "Qwen/Qwen3.6-27B",
    baseModelSlug: "qwen3-6-27b",
    baseModelDisplayName: "Qwen3.6 27B",
    modelKind: "merge",
    downloads: 900,
  });
  const catalog = [qwenBase, llamaBase, outsideBaseLink, qwopus, officialVariant, merge];

  it("lists base labs only after grouping", () => {
    expect(listBaseLabs(catalog)).toEqual(["Meta", "Qwen"]);
  });

  it("nests in-catalog derivatives and leaves outside-base links as ordinary bases", () => {
    const families = browseFamilies(catalog, { lab: "Qwen", search: "", vramGb: 24 });

    expect(families.map((family) => family.base.slug)).toEqual(["qwen3-6-27b", "qwen3-0-6b"]);
    expect(families[0]?.variants.map((variant) => variant.model.slug)).toEqual([
      "qwopus3-6-27b-v2-mtp",
      "qwen3-6-27b-thinking",
      "qwen-llama-merge",
    ]);
    expect(families[1]?.variants).toEqual([]);
  });

  it("derives official variants and lists merges under every catalogued base", () => {
    const families = browseFamilies(catalog, { search: "merge", vramGb: 24 });
    const qwenMerge = families
      .find((family) => family.base.slug === "qwen3-6-27b")
      ?.variants.find((variant) => variant.model.slug === "qwen-llama-merge");
    const llamaMerge = families
      .find((family) => family.base.slug === "llama-3-1-8b")
      ?.variants.find((variant) => variant.model.slug === "qwen-llama-merge");
    const qwenFamily = browseFamilies(catalog, { lab: "Qwen", vramGb: 24 })[0];
    const official = qwenFamily?.variants.find((variant) => variant.model.slug === "qwen3-6-27b-thinking");

    expect(official?.official).toBe(true);
    expect(official?.kind).toBe("finetune");
    expect(qwenMerge?.alsoBasedOn.map((base) => base.displayName)).toEqual(["Llama 3.1 8B"]);
    expect(llamaMerge?.alsoBasedOn.map((base) => base.displayName)).toEqual(["Qwen3.6 27B"]);
  });

  it("matches search across base and variant identity fields", () => {
    const families = browseFamilies(catalog, { search: "jackrong", vramGb: 24 });

    expect(families).toHaveLength(1);
    expect(families[0]?.base.slug).toBe("qwen3-6-27b");
    expect(families[0]?.variants.map((variant) => variant.model.slug)).toContain("qwopus3-6-27b-v2-mtp");
  });

  it("exposes per-row best-fit label data without inventing a fitting quant", () => {
    expect(bestFitForVram(model(), 9).label).toBe("best fit: Q6_K");
    expect(bestFitForVram(model(), 4)).toEqual({ quant: null, label: "no listed quant fits 4 GB" });
  });
});

describe("getOnrampCatalog", () => {
  it("loads the real catalog and trims it to on-ramp models", async () => {
    const catalog = await getOnrampCatalog();
    expect(catalog.popularityAsOf).toBe("2026-07-05");
    expect(catalog.models.length).toBeGreaterThan(50);
    for (const entry of catalog.models) {
      expect(entry.id).toBeTruthy();
      expect(entry.slug).toBeTruthy();
      expect(entry.quants.length).toBeGreaterThan(0);
      expect(entry.likes).toBeGreaterThanOrEqual(0);
      expect(entry.trending).toBeGreaterThanOrEqual(0);
    }
    const qwen = catalog.models.find((entry) => entry.slug === "qwen3-8b");
    expect(qwen).toBeDefined();
    expect(qwen?.ggufRepo).toBeTruthy();
    expect(qwen?.quants.some((quant) => quant.label === "Q4_K_M")).toBe(true);
    expect(catalog.models.some((entry) => entry.baseModelId !== null)).toBe(true);
    expect(catalog.models.every((entry) => Array.isArray(entry.baseModelIds))).toBe(true);
  });
});

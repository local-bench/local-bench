import { describe, expect, it } from "vitest";
import {
  isDerivativeModel,
  listOrgs,
  modelsForOrg,
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

  it("filters real derivatives without treating official pretraining links as fine-tunes", () => {
    const base = model({ slug: "qwen3-6-27b", displayName: "Qwen3.6 27B", downloads: 10 });
    const officialInstruction = model({
      slug: "qwen3-0-6b",
      displayName: "Qwen3 0.6B",
      baseModelId: "Qwen/Qwen3-0.6B-Base",
      baseModelSlug: null,
      baseModelDisplayName: "Qwen/Qwen3-0.6B-Base",
      downloads: 8,
    });
    const fineTune = model({
      slug: "qwopus3-6-27b-v2-mtp",
      displayName: "Qwopus 3.6 27B v2 MTP",
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      modelKind: "finetune",
      downloads: 9,
    });
    const catalog = [base, officialInstruction, fineTune];

    expect(isDerivativeModel(fineTune)).toBe(true);
    expect(isDerivativeModel(officialInstruction)).toBe(false);
    expect(modelsForOrg(catalog, "Qwen", "finetune").map((m) => m.slug)).toEqual(["qwopus3-6-27b-v2-mtp"]);
    expect(modelsForOrg(catalog, "Qwen", "base").map((m) => m.slug)).toEqual(["qwen3-6-27b", "qwen3-0-6b"]);
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
  });
});

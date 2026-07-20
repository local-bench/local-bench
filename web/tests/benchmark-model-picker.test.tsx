import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ModelPicker } from "../components/benchmark-model-picker";
import type { BrowseFamily, OnrampCatalogModel, OnrampCatalogQuant } from "../lib/onramp";

const q4: OnrampCatalogQuant = { label: "Q4_K_M", vramGb8k: 9.2, fileGb: 8.1, bpw: 4.8 };

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
    quants: [q4],
    ...overrides,
  };
}

function family(base: OnrampCatalogModel, variants: BrowseFamily["variants"] = []): BrowseFamily {
  return {
    base,
    variants,
  };
}

function baseProps() {
  const selected = model();
  return {
    popular: [{ model: selected, quant: q4 }],
    popularSlug: "qwen3-8b",
    onPopular: vi.fn(),
    popularitySort: "downloads" as const,
    onPopularitySort: vi.fn(),
    vramGb: 24,
    popularityAsOf: "2026-07-05",
    orgs: ["Qwen"],
    browseOrg: "Qwen",
    onOrg: vi.fn(),
    browseSearch: "",
    onBrowseSearch: vi.fn(),
    families: [family(selected)],
    browseSlug: "qwen3-8b",
    browseModel: selected,
    onModel: vi.fn(),
    browseQuant: "Q4_K_M",
    onQuant: vi.fn(),
    pasteRepo: "",
    onPasteRepo: vi.fn(),
    pasteHfModelId: "",
    onPasteHfModelId: vi.fn(),
    pasteQuant: "Q4_K_M",
    onPasteQuant: vi.fn(),
    benchmarkedModels: [],
  };
}

describe("ModelPicker", () => {
  it("renders popularity stats, the three sort controls, and the repo-level disclaimer", () => {
    const html = renderToStaticMarkup(createElement(ModelPicker, { ...baseProps(), mode: "popular" }));
    expect(html).toContain("Popular models with 8k-context VRAM estimates for 24 GB");
    expect(html).toContain("sorted by HF downloads last month");
    expect(html).toContain("popularity as of 2026-07-05");
    expect(html).toContain("Downloads");
    expect(html).toContain("Trending");
    expect(html).toContain("Likes");
    expect(html).toContain("↓ 11M downloads/mo · ♥ 420");
    expect(html).toContain("Hugging Face popularity is repo-level");
    expect(html).toContain("ranked recipe pins 32k context");
    expect(html).toContain("only chipped entries have measured local-bench runs");
    expect(html).toContain("no run yet — benchmark it");
  });

  it("links measured popular entries to their trailing-slash model page", () => {
    const html = renderToStaticMarkup(createElement(ModelPicker, {
      ...baseProps(),
      mode: "popular",
      benchmarkedModels: [{ score: 61.2, slug: "qwen3-8b" }],
    }));

    expect(html).toContain('href="/model/qwen3-8b/"');
    expect(html).toContain("benched 61.2 →");
    expect(html).not.toContain("no run yet — benchmark it");
  });

  it("renders base-only browse families with search, original release, and VRAM fit labels", () => {
    const selected = model({ quants: [{ label: "Q8_0", vramGb8k: 48, fileGb: 12, bpw: 8.5 }] });
    const html = renderToStaticMarkup(
      createElement(ModelPicker, {
        ...baseProps(),
        mode: "browse",
        browseSlug: selected.slug,
        browseModel: selected,
        families: [family(selected)],
      }),
    );

    expect(html).toContain('aria-label="Base lab"');
    expect(html).toContain('placeholder="Search model / creator / repo..."');
    expect(html).toContain("Original release");
    expect(html).toContain("base only — no curated variants for this base yet");
    expect(html).toContain("no listed quant fits 24 GB");
    expect(html).not.toContain("All");
    expect(html).not.toContain("Fine-tunes");
  });

  it("auto-expands small families and renders variant attribution", () => {
    const base = model({ slug: "qwen3-6-27b", displayName: "Qwen3.6 27B", id: "Qwen/Qwen3.6-27B" });
    const fineTune = model({
      slug: "qwopus",
      displayName: "Qwopus3.6 27B v2 MTP",
      org: "Jackrong",
      baseModelIds: ["Qwen/Qwen3.6-27B"],
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      downloads: 2_400,
      likes: 55,
      modelKind: "finetune",
    });
    const html = renderToStaticMarkup(
      createElement(ModelPicker, {
        ...baseProps(),
        mode: "browse",
        browseSlug: fineTune.slug,
        browseModel: fineTune,
        families: [
          family(base, [
            {
              model: fineTune,
              kind: "finetune",
              official: false,
              alsoBasedOn: [],
            },
          ]),
        ],
      }),
    );
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("Qwopus3.6 27B v2 MTP");
    expect(html).toContain("Fine-tune");
    expect(html).toContain("by Jackrong");
    expect(html).toContain("↓ 2.4K downloads/mo · ♥ 55");
    expect(html).toContain("best fit: Q4_K_M");
  });

  it("collapses medium families and caps large expanded families behind show all", () => {
    const base = model({ slug: "qwen3-6-27b", displayName: "Qwen3.6 27B", id: "Qwen/Qwen3.6-27B" });
    const mediumVariants = [1, 2, 3, 4].map((index) => ({
      model: model({
        slug: `variant-${index}`,
        displayName: `Variant ${index}`,
        org: "Tuner",
        baseModelIds: [base.id],
        baseModelId: base.id,
        baseModelSlug: base.slug,
        baseModelDisplayName: base.displayName,
        modelKind: "finetune",
      }),
      kind: "finetune" as const,
      official: false,
      alsoBasedOn: [],
    }));
    const largeVariants = [1, 2, 3, 4, 5, 6].map((index) => ({
      model: model({
        slug: `large-variant-${index}`,
        displayName: `Large Variant ${index}`,
        org: "Tuner",
        baseModelIds: [base.id],
        baseModelId: base.id,
        baseModelSlug: base.slug,
        baseModelDisplayName: base.displayName,
        modelKind: "finetune",
      }),
      kind: "finetune" as const,
      official: false,
      alsoBasedOn: [],
    }));

    const mediumHtml = renderToStaticMarkup(
      createElement(ModelPicker, {
        ...baseProps(),
        mode: "browse",
        browseSlug: "",
        browseModel: null,
        families: [family(base, mediumVariants)],
      }),
    );
    const largeHtml = renderToStaticMarkup(
      createElement(ModelPicker, {
        ...baseProps(),
        mode: "browse",
        browseSlug: "",
        browseModel: null,
        browseSearch: "variant",
        families: [family(base, largeVariants)],
      }),
    );

    expect(mediumHtml).toContain('aria-expanded="false"');
    expect(mediumHtml).toContain("4 variants");
    expect(mediumHtml).not.toContain("Variant 1");
    expect(largeHtml).toContain("Large Variant 5");
    expect(largeHtml).not.toContain("Large Variant 6");
    expect(largeHtml).toContain("Show all 6 variants");
  });

  it("renders paste fields for the GGUF repo and optional exact HF identity repo", () => {
    const html = renderToStaticMarkup(createElement(ModelPicker, { ...baseProps(), mode: "paste" }));
    expect(html).toContain("HF GGUF repo");
    expect(html).toContain("Exact HF model repo");
    expect(html).toContain("Use the fine-tune");
    expect(html).toContain("Do not enter the base model");
    expect(html).toContain("Pick the quant label that exists in the GGUF repo");
  });
});

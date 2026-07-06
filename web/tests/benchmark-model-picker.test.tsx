import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ModelPicker } from "../components/benchmark-model-picker";
import type { OnrampCatalogModel, OnrampCatalogQuant } from "../lib/onramp";

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
    baseModelId: null,
    baseModelSlug: null,
    baseModelDisplayName: null,
    quants: [q4],
    ...overrides,
  };
}

function baseProps() {
  return {
    popular: [{ model: model(), quant: q4 }],
    popularSlug: "qwen3-8b",
    onPopular: vi.fn(),
    popularitySort: "downloads" as const,
    onPopularitySort: vi.fn(),
    vramGb: 24,
    popularityAsOf: "2026-07-05",
    orgs: ["Qwen"],
    browseOrg: "Qwen",
    onOrg: vi.fn(),
    orgModels: [model()],
    browseType: "all" as const,
    onBrowseType: vi.fn(),
    browseSlug: "qwen3-8b",
    onModel: vi.fn(),
    browseQuant: "Q4_K_M",
    onQuant: vi.fn(),
    pasteRepo: "",
    onPasteRepo: vi.fn(),
    pasteQuant: "Q4_K_M",
    onPasteQuant: vi.fn(),
  };
}

describe("ModelPicker", () => {
  it("renders popularity stats, the three sort controls, and the repo-level disclaimer", () => {
    const html = renderToStaticMarkup(createElement(ModelPicker, { ...baseProps(), mode: "popular" }));
    expect(html).toContain("Popular models that fit 24 GB VRAM");
    expect(html).toContain("sorted by HF downloads last month");
    expect(html).toContain("popularity as of 2026-07-05");
    expect(html).toContain("Downloads");
    expect(html).toContain("Trending");
    expect(html).toContain("Likes");
    expect(html).toContain("↓ 11M downloads/mo · ♥ 420");
    expect(html).toContain("Hugging Face popularity is repo-level");
  });

  it("renders browse rows with inline popularity and fine-tune lineage", () => {
    const fineTune = model({
      slug: "qwopus",
      displayName: "Qwopus3.6 27B v2 MTP",
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      downloads: 2_400,
      likes: 55,
      modelKind: "finetune",
    });
    const html = renderToStaticMarkup(
      createElement(ModelPicker, { ...baseProps(), mode: "browse", browseSlug: fineTune.slug, orgModels: [fineTune] }),
    );
    expect(html).toContain("Qwopus3.6 27B v2 MTP");
    expect(html).toContain("fine-tune of Qwen3.6 27B");
    expect(html).toContain("↓ 2.4K downloads/mo · ♥ 55");
  });

  it("filters browse rows to real fine-tunes and links lineage chips to catalog bases", () => {
    const base = model({ slug: "qwen3-6-27b", displayName: "Qwen3.6 27B" });
    const officialInstruction = model({
      slug: "qwen3-0-6b",
      displayName: "Qwen3 0.6B",
      baseModelId: "Qwen/Qwen3-0.6B-Base",
      baseModelDisplayName: "Qwen/Qwen3-0.6B-Base",
    });
    const fineTune = model({
      slug: "qwopus3-6-27b-v2-mtp",
      displayName: "Qwopus 3.6 27B v2 MTP",
      baseModelId: "Qwen/Qwen3.6-27B",
      baseModelSlug: "qwen3-6-27b",
      baseModelDisplayName: "Qwen3.6 27B",
      modelKind: "finetune",
      downloads: 292_588,
      likes: 322,
    });

    const html = renderToStaticMarkup(
      createElement(ModelPicker, {
        ...baseProps(),
        mode: "browse",
        browseType: "finetune",
        browseSlug: fineTune.slug,
        orgModels: [base, officialInstruction, fineTune],
      }),
    );

    expect(html).toContain("All");
    expect(html).toContain("Base");
    expect(html).toContain("Fine-tunes");
    expect(html).toContain("Qwopus 3.6 27B v2 MTP");
    expect(html).toContain("↓ 292.6K downloads/mo · ♥ 322");
    expect(html).toContain('href="/model/qwen3-6-27b"');
    expect(html).toContain("fine-tune of Qwen3.6 27B");
    expect(html).not.toContain("Qwen3 0.6B");
  });

  it("tells paste users to submit the fine-tune GGUF repo itself", () => {
    const html = renderToStaticMarkup(createElement(ModelPicker, { ...baseProps(), mode: "paste" }));
    expect(html).toContain("Fine-tunes are first-class");
    expect(html).toContain("paste the fine-tune");
    expect(html).toContain("comparisons against the base come from benchmarking both");
  });
});

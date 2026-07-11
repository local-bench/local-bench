import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const trustedRun = {
  axes: {}, composite: { hi: 85, lo: 85, point: 85 }, demo: false, est_cost_usd: null,
  file_gb: 10, hardware: { cpu: null, gpu: null, os: null, ram_gb: null }, lane: "bounded-final-v2",
  n_errors: 0, n_items: 10, origin: "project_anchor", quant_label: "Q4_K_M", ranked: true,
  run_id: "trusted-run", runtime: { ctx_len_configured: 8192, kv_cache_quant: "q8_0", name: "llama.cpp", parallel_slots: 1, version: "trusted-runtime" },
  score_status: "measured", tier: "standard", tok_s: 20, tokens_to_answer_median: 10,
  trust_label: "project_anchor", vram_footprint_gb: 12,
};
const communityRun = {
  ...trustedRun, composite: { hi: 100, lo: 100, point: 100 }, origin: "community", quant_label: "Q2_K",
  run_id: "community-run", runtime: { ...trustedRun.runtime, version: "community-runtime" },
  trust_label: "community_self_submitted",
};

vi.mock("@/lib/data", () => ({
  getModelStaticParams: async () => [{ slug: "fixture-model" }],
  getModelPageData: async () => ({
    anchorRuns: [], familyModels: [], lineage: null,
    model: { demo: false, family: "Fixture", kind: "community", model_kind: "base", model_label: "Fixture Model", runs: [trustedRun, communityRun], slug: "fixture-model" },
    vsBaseComparisons: [],
  }),
}));

describe("model page trusted population", () => {
  it("renders runtime, scatter, and variant consumers without community rank leakage", async () => {
    const { default: ModelPage } = await import("../app/model/[slug]/page");
    const element = await ModelPage({ params: Promise.resolve({ slug: "fixture-model" }) });
    const html = renderToStaticMarkup(createElement(() => element));
    expect(html).toContain("trusted-runtime");
    expect(html).toContain("trusted-run");
    expect(html).not.toContain("community-runtime");
    expect(html).not.toContain("community-run");
  });
});

import { describe, expect, it } from "vitest";
import {
  getIndexData,
  getModelData,
  getModelPageData,
  getModelStaticParams,
  getRunStaticParams,
} from "../lib/data";
import { splitLeaderboard } from "../lib/leaderboard";

describe("static data access", () => {
  it("loads every catalog model as a score-less shell in the index", async () => {
    // Given an empty benchmark source list and the checked-in model catalog.
    // When the generated index is loaded.
    const index = await getIndexData();
    const qwen = index.models.find((model) => model.slug === "qwen3-0-6b");

    // Then the catalog is browsable without invented benchmark scores: 102 catalog shells.
    // (The standalone Qwopus3.6-27B-MTP distill *board row* was removed in eabc121 as an
    // inferior self-distill of Qwen3.6-27B; its catalog browse-shells remain in the 102.)
    expect(index.models).toHaveLength(102);
    expect(qwen).toMatchObject({
      best_run_id: null,
      composite: null,
      model_label: "Qwen3 0.6B",
      n_runs: 0,
      score_status: "missing",
    });
  });

  it("emits per-answer latency for measured runs but omits it on catalog shells", async () => {
    const model = await getModelData("qwen3-6-27b");
    const measured = model.runs.find((run) => run.run_id !== null && run.composite !== null);
    expect(measured).toBeDefined();
    expect(typeof measured?.latency_s_median).toBe("number");
    expect(measured?.latency_s_median ?? 0).toBeGreaterThan(0);
    // Catalog shells omit the field -> undefined (the board renders "—").
    const index = await getIndexData();
    expect(index.models.find((model) => model.slug === "qwen3-0-6b")?.latency_s_median).toBeUndefined();
  });

  it("carries total bench wall time on measured index rows but omits it on catalog shells", async () => {
    const index = await getIndexData();
    const measured = index.models.find((model) => model.slug === "qwen3-6-27b");
    expect(typeof measured?.wall_time_seconds).toBe("number");
    expect(measured?.wall_time_seconds ?? 0).toBeGreaterThan(0);
    // Catalog shells omit the field -> undefined (the board renders "—" via formatDuration).
    expect(index.models.find((model) => model.slug === "qwen3-0-6b")?.wall_time_seconds).toBeUndefined();
  });

  it("splits the leaderboard so score-less shells never enter the ranked board", async () => {
    const index = await getIndexData();
    const { ranked, catalog } = splitLeaderboard(index.models);
    // The ranked board is the measured, conformance-passing, capped-thinking headline scope.
    expect(ranked.length).toBeGreaterThan(0);
    expect(ranked.every((m) => m.composite !== null && m.ranked && m.lane === "capped-thinking")).toBe(true);
    expect(ranked.some((m) => m.score_status === "missing")).toBe(false);
    // The catalog view is only score-less shells; no measured row leaks in.
    expect(catalog.length).toBeGreaterThan(0);
    expect(catalog.every((m) => m.composite === null)).toBe(true);
  });

  it("keeps a catalog-only model as quant shells while measured runs add run-detail params", async () => {
    // Given a model that exists only in the catalog.
    // When the model page data and static route params are assembled.
    const pageData = await getModelPageData("qwen3-0-6b");
    const modelParams = await getModelStaticParams();
    const runParams = await getRunStaticParams();

    // Then the catalog-only model still renders data-ready quant shells (no fake run receipts
    // of its own), while the 6 wired 27B-campaign runs contribute the run-detail params.
    expect(modelParams).toContainEqual({ slug: "qwen3-0-6b" });
    expect(runParams).toHaveLength(6);
    expect(pageData.model.model_label).toBe("Qwen3 0.6B");
    expect(pageData.model.runs.map((run) => [run.quant_label, run.file_gb, run.vram_required_gb_8k, run.run_id, run.composite])).toEqual([
      ["Q8_0", 0.6, 1.7, null, null],
      ["Q6_K", 0.5, 1.5, null, null],
      ["Q5_K_M", 0.4, 1.5, null, null],
      ["Q4_K_M", 0.4, 1.4, null, null],
      ["Q3_K_M", 0.3, 1.3, null, null],
      ["Q2_K", 0.2, 1.3, null, null],
    ]);
  });
});

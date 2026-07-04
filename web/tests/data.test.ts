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

    // Then the catalog is browsable without invented benchmark scores, while curated
    // non-catalog benchmark rows may add measured community models to the index.
    // (The standalone Qwopus3.6-27B-MTP distill *board row* was removed in eabc121 as an
    // inferior self-distill of Qwen3.6-27B; its catalog browse-shells remain in the 102.)
    expect(index.models.map((model) => model.slug)).toContain("gemma-4-12b-coder-fable5");
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
    const { ranked, staticComposite, catalog } = splitLeaderboard(index.models);
    expect(ranked.some((m) => m.slug === "gemma-4-12b-it-q4-k-xl")).toBe(true);
    expect(ranked.every((m) => m.composite !== null && m.ranked && m.lane === "capped-thinking")).toBe(true);
    expect(ranked.some((m) => m.score_status === "missing")).toBe(false);
    expect(staticComposite.every((m) => m.composite_static !== null && m.static_index_version === "static-suite-v1")).toBe(true);
    // The catalog view is only score-less shells; no measured row leaks in.
    expect(catalog.length).toBeGreaterThan(0);
    expect(catalog.every((m) => m.composite === null)).toBe(true);
  });

  it("surfaces the ranked Gemma proof row with project-anchor attested provenance", async () => {
    const index = await getIndexData();
    const proof = index.models.find((model) => model.slug === "gemma-4-12b-it-q4-k-xl");

    expect(proof).toMatchObject({
      agentic_provenance: "project_attested",
      best_run_id: "gemma-4-12b-it-q4-k-xl__localbench-run",
      origin: "project_anchor",
      ranked: true,
      static_index_version: "static-suite-v1",
      trust_label: "project_anchor",
    });
    expect(proof?.axes["agentic"]?.point).toBeGreaterThan(5);
    expect(proof?.composite_full?.point).toBeCloseTo(40.26, 1);
    expect(proof?.composite_static?.point).toBeGreaterThan(70);
  });

  it("keeps a catalog-only model as quant shells while measured runs add run-detail params", async () => {
    // Given a model that exists only in the catalog.
    // When the model page data and static route params are assembled.
    const pageData = await getModelPageData("qwen3-0-6b");
    const modelParams = await getModelStaticParams();
    const runParams = await getRunStaticParams();

    // Then the catalog-only model still renders data-ready quant shells (no fake run receipts
    // of its own), while wired measured campaign runs contribute the run-detail params.
    expect(modelParams).toContainEqual({ slug: "qwen3-0-6b" });
    expect(runParams.map((param) => param.runId).filter((runId) => runId.startsWith("qwen3-0-6b__"))).toEqual([]);
    expect(runParams).toEqual(
      expect.arrayContaining([
        { runId: "gemma-4-12b-it__gemma-4-12b-it-Q3_K_M" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-Q4_K_M" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-Q5_K_M" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-Q6_K" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-Q8_0" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-BF16" },
        { runId: "gemma-4-12b-it__gemma-4-12b-it-UD-Q2_K_XL" },
        { runId: "gemma-4-12b-coder-fable5__gemma-4-12b-coder-fable5-Q8_0" },
        { runId: "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q4" },
        { runId: "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q6" },
        { runId: "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q8" },
        { runId: "qwen3-coder-next__qwen3-coder-next-q6" },
        { runId: "qwen3-coder-next__qwen3-coder-next-q8" },
      ]),
    );
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

  it("reflects the Gemma ladder while quarantining invalid agentic scores", async () => {
    const index = await getIndexData();
    const gemmaIndex = index.models.find((model) => model.slug === "gemma-4-12b-it");
    const coderIndex = index.models.find((model) => model.slug === "gemma-4-12b-coder-fable5");
    const gemma = await getModelData("gemma-4-12b-it");
    const coder = await getModelData("gemma-4-12b-coder-fable5");

    expect(gemmaIndex).toMatchObject({
      n_runs: 7,
      ranked: false,
      score_status: "measured",
    });
    expect(gemmaIndex?.axes["agentic"]).toBeUndefined();
    expect(gemma.runs).toHaveLength(7);
    expect(gemma.runs.every((run) => run.axes["agentic"] === undefined)).toBe(true);
    expect(gemma.runs.every((run) => run.ranked === false)).toBe(true);
    expect(gemma.runs.map((run) => run.run_id)).toEqual(
      expect.arrayContaining([
        "gemma-4-12b-it__gemma-4-12b-it-Q8_0",
        "gemma-4-12b-it__gemma-4-12b-it-Q6_K",
        "gemma-4-12b-it__gemma-4-12b-it-Q5_K_M",
        "gemma-4-12b-it__gemma-4-12b-it-Q4_K_M",
        "gemma-4-12b-it__gemma-4-12b-it-Q3_K_M",
        "gemma-4-12b-it__gemma-4-12b-it-UD-Q2_K_XL",
        "gemma-4-12b-it__gemma-4-12b-it-BF16",
      ]),
    );

    expect(coderIndex).toMatchObject({
      n_runs: 1,
      ranked: false,
      score_status: "measured",
    });
    expect(coderIndex?.axes["agentic"]).toBeUndefined();
    expect(coder.runs).toHaveLength(1);
    expect(coder.runs[0]?.run_id).toBe("gemma-4-12b-coder-fable5__gemma-4-12b-coder-fable5-Q8_0");
    expect(coder.runs[0]?.axes["agentic"]).toBeUndefined();
    expect(coder.runs[0]?.ranked).toBe(false);
  });

  it("surfaces Qwen3.6 distills as agentic-only model variants", async () => {
    // Given the Qwen3.6-27B model page data generated from curated sources.
    const model = await getModelData("qwen3-6-27b");

    // When the two distill rows are selected.
    const opus = model.runs.find((run) => run.quant_label === "Opus distill (Q4_K_M)");
    const coder = model.runs.find((run) => run.quant_label === "Coder distill (NVFP4)");

    // Then they carry agentic ASR only: no full headline profile, no Index, and no run receipt.
    expect(opus).toMatchObject({
      composite: null,
      lane: "agentic-only",
      run_id: null,
      score_status: "measured",
    });
    expect(opus?.axes.agentic.point).toBeCloseTo(12.5, 4);
    expect(opus?.axes.knowledge).toBeUndefined();
    expect(opus?.axes.instruction).toBeUndefined();

    expect(coder).toMatchObject({
      composite: null,
      lane: "agentic-only",
      run_id: null,
      score_status: "measured",
    });
    expect(coder?.axes.agentic.point).toBeCloseTo(11.9792, 4);
    expect(coder?.axes.knowledge).toBeUndefined();
    expect(coder?.axes.instruction).toBeUndefined();
  });

  it("surfaces catalog-backed Vast runs as measured quant rows", async () => {
    // Given the completed Vast run JSONs have been curated into the public projection.
    const qwen35 = await getModelData("qwen3-6-35b-a3b");
    const coderNext = await getModelData("qwen3-coder-next");

    // When measured rows are selected from each catalog-backed model page.
    const qwen35Rows = qwen35.runs.filter((run) => run.score_status === "measured");
    const coderNextRows = coderNext.runs.filter((run) => run.score_status === "measured");

    // Then the completed Vast rungs carry run receipts and measured Index data.
    expect(qwen35Rows.map((run) => run.run_id)).toEqual([
      "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q8",
      "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q6",
      "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q4",
    ]);
    expect(coderNextRows.map((run) => run.run_id)).toEqual([
      "qwen3-coder-next__qwen3-coder-next-q8",
      "qwen3-coder-next__qwen3-coder-next-q6",
    ]);
    expect(qwen35Rows.every((run) => run.composite !== null && run.lane === "capped-thinking")).toBe(true);
    expect(coderNextRows.every((run) => run.composite !== null && run.lane === "capped-thinking")).toBe(true);
  });
});

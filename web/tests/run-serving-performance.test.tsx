import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RunPage, { ServingPerformanceCard } from "../app/run/[runId]/page";
import { RunDetailSchema, type RunDetail } from "../lib/schemas";

describe("ServingPerformanceCard", () => {
  it("renders llama.cpp timings against the run hardware when perf is present", () => {
    const html = renderToStaticMarkup(createElement(ServingPerformanceCard, { run: fixtureRun() }));
    expect(html).toContain("Serving performance");
    expect(html).toContain("RTX 4090");
    expect(html).toContain("prefill");
    expect(html).toContain("812.3 tok/s");
    expect(html).toContain("decode");
    expect(html).toContain("42.4 tok/s");
    expect(html).toContain("TTFT proxy");
    expect(html).toContain("prompt processing before first token");
    expect(html).toContain("non-streaming harness, lower bound");
    expect(html).toContain("91.0%");
    expect(html).toContain("bigcodebench_hard");
    expect(html).toContain("Source: llama.cpp server timings.");
  });

  it("renders nothing when perf is absent", () => {
    const run = fixtureRun();
    const runWithoutPerf = RunDetailSchema.parse(Object.fromEntries(Object.entries(run).filter(([key]) => key !== "perf")));
    const html = renderToStaticMarkup(createElement(ServingPerformanceCard, { run: runWithoutPerf }));
    expect(html).toBe("");
  });
});

describe("RunPage legacy receipts", () => {
  it("renders previous-index diagnostics without current Index hero framing", async () => {
    // Given a published receipt whose model-page metadata marks it as a retired-lane measurement.
    const html = renderToStaticMarkup(
      await RunPage({
        params: Promise.resolve({ runId: "gemma-4-12b-it__gemma-4-12b-it-Q8_0" }),
      }),
    );

    // When the receipt is rendered, then it keeps the original labels but with retired-lane framing.
    expect(html).toContain("Previous-index diagnostics");
    expect(html).toContain("retired lane");
    expect(html).toContain("suite-v1 | retired lane capped-thinking");
    expect(html).toContain("Diagnostic score (retired lane)");
    expect(html).toContain("capped-thinking");
    expect(html).not.toContain("Local Intelligence Index</div><div class=\"font-mono text-xs text-bench-accent\">index-v3.0");
    expect(html).not.toContain("text-6xl");
  });
});

function fixtureRun(): RunDetail {
  return RunDetailSchema.parse({
    axes: {},
    composite: { hi: 90, lo: 80, point: 85 },
    demo: false,
    est_cost_usd: null,
    index_version: "index-v3.0",
    item_set_hashes: {},
    kind: "community",
    manifest_summary: {
      caps: {},
      hardware: {
        cpu: "Ryzen",
        gpu: { driver: "560", name: "RTX 4090", vram_gb: 24, vram_mb: 24_576 },
        os: "Linux",
        ram_gb: 64,
      },
      lane: "bounded-final-v1",
      model: {
        family: "Fixture",
        file_name: "fixture.gguf",
        file_sha256: "a".repeat(64),
        file_size_bytes: 1_000,
        format: "gguf",
        runtime_reported_model: "fixture",
      },
      quant: "Q4_K_M",
      runtime: {
        ctx_len_configured: 8192,
        kv_cache_quant: "q8_0",
        name: "llama.cpp",
        parallel_slots: 1,
        version: "b1234",
      },
      sampling: { by_bench: {}, temperature: 0, thinking_mode: "bounded" },
      thinking_mode: "bounded",
    },
    model_label: "Fixture Model",
    perf: {
      decode_tps: 42.4,
      per_bench: {
        bigcodebench_hard: {
          decode_tps: 40,
          n: 12,
          prefill_tps: 800,
          prompt_ms_median: 128,
        },
      },
      prefill_tps: 812.3,
      predicted_ms_median: 3_100,
      predicted_ms_p95: 4_400,
      prompt_ms_median: 122,
      prompt_ms_p95: 250,
      timings_coverage: 0.91,
      timings_source: "llama.cpp",
      ttft_proxy_ms_median: 125,
    },
    ranked: true,
    run_id: "fixture-run",
    suite_version: "suite-v2",
    tier: "standard",
    tokens_to_answer_median: 128,
    tokens_to_answer_p95: 256,
    totals: {
      completion_tokens: 2_000,
      completion_tokens_per_second: 42,
      n_errors: 0,
      n_items: 12,
      prompt_tokens: 10_000,
      total_tokens: 12_000,
      wall_time_seconds: 300,
    },
    worst_axis: { bench: "knowledge", point: 80, point_raw: 0.8 },
  });
}

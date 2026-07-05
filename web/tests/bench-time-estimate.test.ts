import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import {
  EFFECTIVE_UTILIZATION,
  SUITE_GENERATED_TOKENS,
  bandwidthRangeForTier,
  decodeSeconds,
  estimateBenchTime,
  formatBenchTimeRange,
} from "../lib/bench-time-estimate";
import { BenchmarkOnramp } from "../components/benchmark-onramp";
import type { OnrampCatalogModel } from "../lib/onramp";

// Measured board runs (web/public/data/runs/*.json totals + manifest_summary), both on
// RTX 5090 (spec 1792 GB/s). These pin the calibration; if the constants drift, these fail.
const RTX_5090_GBPS = 1792;
// gemma-4-12b-it__localbench-run: full five-axis ranked run, QAT Q4_K_XL file 6,716,355,328 B.
const RUN_A = { completionTokens: 6_095_115, wallSeconds: 59_274.17, fileGb: 6.716355328 };
// gemma-4-31b-it__ladder-gemma4-31b-Q4_K_M: static-axes run, catalog Q4_K_M file 18.8 GB.
const RUN_B = { completionTokens: 2_713_578, wallSeconds: 44_835.84, fileGb: 18.8 };

describe("calibration against measured board runs", () => {
  it("reproduces the five-axis gemma-4-12b-it wall time within ±40%", () => {
    const predicted = decodeSeconds(RUN_A.completionTokens, RUN_A.fileGb, RTX_5090_GBPS);
    expect(predicted / RUN_A.wallSeconds).toBeGreaterThan(0.6);
    expect(predicted / RUN_A.wallSeconds).toBeLessThan(1.4);
  });

  it("reproduces the static-axes gemma-4-31b-it wall time within ±40%", () => {
    const predicted = decodeSeconds(RUN_B.completionTokens, RUN_B.fileGb, RTX_5090_GBPS);
    expect(predicted / RUN_B.wallSeconds).toBeGreaterThan(0.6);
    expect(predicted / RUN_B.wallSeconds).toBeLessThan(1.4);
  });

  it("suite token constant matches the measured five-axis completion total within 5%", () => {
    expect(SUITE_GENERATED_TOKENS / RUN_A.completionTokens).toBeGreaterThan(0.95);
    expect(SUITE_GENERATED_TOKENS / RUN_A.completionTokens).toBeLessThan(1.05);
  });

  it("brackets the measured five-axis wall time on the 32 GB tier", () => {
    const estimate = estimateBenchTime({ fileGb: RUN_A.fileGb, paramsB: 12, bpw: 4.5, vramGb8k: 8.4, vramGb: 32 });
    expect(estimate).not.toBeNull();
    expect(estimate?.rough).toBe(false);
    expect(estimate?.lowSeconds).toBeLessThan(RUN_A.wallSeconds);
    expect(estimate?.highSeconds).toBeGreaterThan(RUN_A.wallSeconds);
  });

  it("keeps the 32 GB tier's fast edge at the calibration card's spec bandwidth", () => {
    // 1800 is the table's rounding of the RTX 5090's 1792 GB/s.
    expect(bandwidthRangeForTier(32).high).toBeGreaterThanOrEqual(RTX_5090_GBPS);
    expect(EFFECTIVE_UTILIZATION).toBe(0.5);
  });
});

describe("estimateBenchTime fit handling", () => {
  it("returns null when the quant's 8K-context requirement exceeds the tier", () => {
    expect(estimateBenchTime({ fileGb: 22.3, paramsB: 27, bpw: 6.6, vramGb8k: 24.6, vramGb: 24 })).toBeNull();
  });

  it("returns an estimate when the quant exactly fits the tier", () => {
    expect(estimateBenchTime({ fileGb: 22.3, paramsB: 27, bpw: 6.6, vramGb8k: 24, vramGb: 24 })).not.toBeNull();
  });

  it("falls back to weight size for the fit check when vramGb8k is missing", () => {
    expect(estimateBenchTime({ fileGb: 30, paramsB: null, bpw: null, vramGb8k: null, vramGb: 24 })).toBeNull();
    expect(estimateBenchTime({ fileGb: 20, paramsB: null, bpw: null, vramGb8k: null, vramGb: 24 })).not.toBeNull();
  });
});

describe("estimateBenchTime size fallbacks", () => {
  it("derives weight bytes from paramsB × bpw / 8 when fileGb is null", () => {
    const fromParams = estimateBenchTime({ fileGb: null, paramsB: 12, bpw: 4.85, vramGb8k: 8.9, vramGb: 24 });
    const fromFile = estimateBenchTime({ fileGb: (12 * 4.85) / 8, paramsB: null, bpw: null, vramGb8k: 8.9, vramGb: 24 });
    expect(fromParams).not.toBeNull();
    expect(fromParams?.rough).toBe(false);
    expect(fromParams?.lowSeconds).toBeCloseTo(fromFile?.lowSeconds ?? Number.NaN, 6);
    expect(fromParams?.highSeconds).toBeCloseTo(fromFile?.highSeconds ?? Number.NaN, 6);
  });

  it("returns a wide rough range for pasted repos with no size metadata", () => {
    const estimate = estimateBenchTime({ fileGb: null, paramsB: null, bpw: null, vramGb8k: null, vramGb: 24 });
    expect(estimate).not.toBeNull();
    expect(estimate?.rough).toBe(true);
    expect(estimate?.lowSeconds).toBeGreaterThan(0);
    // Wide by construction: weight assumption alone spans 0.3-0.7 of the tier.
    expect((estimate?.highSeconds ?? 0) / (estimate?.lowSeconds ?? 1)).toBeGreaterThan(4);
  });

  it("scales with model size within a tier", () => {
    const small = estimateBenchTime({ fileGb: 7.3, paramsB: 12, bpw: 4.85, vramGb8k: 8.9, vramGb: 24 });
    const large = estimateBenchTime({ fileGb: 12.8, paramsB: 12, bpw: 8.5, vramGb8k: 14.4, vramGb: 24 });
    expect(large?.lowSeconds ?? 0).toBeGreaterThan(small?.lowSeconds ?? 0);
    expect(large?.highSeconds ?? 0).toBeGreaterThan(small?.highSeconds ?? 0);
  });
});

describe("formatBenchTimeRange", () => {
  it("formats sub-90-minute ranges in minutes rounded to 5", () => {
    expect(formatBenchTimeRange(45 * 60, 90 * 60)).toBe("~45–90 min");
    expect(formatBenchTimeRange(43 * 60, 88 * 60)).toBe("~45–90 min");
  });

  it("formats hour ranges", () => {
    expect(formatBenchTimeRange(2 * 3600, 4 * 3600)).toBe("~2–4 h");
    expect(formatBenchTimeRange(1.4 * 3600, 3.1 * 3600)).toBe("~1.5–3 h");
    expect(formatBenchTimeRange(9 * 3600, 32 * 3600)).toBe("~9–32 h");
  });

  it("collapses ranges that round to the same value", () => {
    expect(formatBenchTimeRange(44 * 60, 46 * 60)).toBe("~45 min");
    expect(formatBenchTimeRange(3.9 * 3600, 4.1 * 3600)).toBe("~4 h");
  });

  it("floors tiny durations at 5 min and orders swapped inputs", () => {
    expect(formatBenchTimeRange(30, 60)).toBe("~5 min");
    expect(formatBenchTimeRange(4 * 3600, 2 * 3600)).toBe("~2–4 h");
  });
});

describe("bench time panel in the onramp header", () => {
  const catalog: readonly OnrampCatalogModel[] = [
    {
      id: "google/gemma-4-12B-it",
      slug: "gemma-4-12b-it",
      displayName: "Gemma 4 12B IT",
      family: "Gemma 4",
      org: "Google",
      paramsB: 12,
      reasoningCapable: true,
      license: "apache-2.0",
      ggufRepo: "unsloth/gemma-4-12b-it-GGUF",
      downloads: 1_309_625,
      quants: [
        { label: "Q8_0", vramGb8k: 14.4, fileGb: 12.8, bpw: 8.5 },
        { label: "Q4_K_M", vramGb8k: 8.9, fileGb: 7.3, bpw: 4.85 },
      ],
    },
  ];

  it("renders a range for the default selection and a placeholder when nothing fits", () => {
    const withModel = renderToStaticMarkup(createElement(BenchmarkOnramp, { catalog }));
    expect(withModel).toContain("Estimated benchmark time");
    expect(withModel).toContain("full five-axis suite on your 24 GB tier");
    expect(withModel).toMatch(/~[\d.]+–[\d.]+ (h|min)/);

    const empty = renderToStaticMarkup(createElement(BenchmarkOnramp, { catalog: [] }));
    expect(empty).toContain("Estimated benchmark time");
    expect(empty).toContain("pick a model");
  });
});

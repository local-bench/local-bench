// Wall-time estimate for running the full five-axis suite (the on-ramp recipe) on the
// user's VRAM tier. Model: dense decode is memory-bound, so tok/s ≈ effective memory
// bandwidth / weight bytes; suite wall time ≈ suite generated tokens × weight bytes /
// (bandwidth × utilization). Calibrated against measured runs in web/public/data (below).
//
// Known bias: MoE models (catalog paramsB = total params, fileGb = full expert file) touch
// only their active experts per token, so this estimate reads high for them.

export type BenchTimeInput = {
  readonly fileGb: number | null;
  readonly paramsB: number | null;
  readonly bpw: number | null;
  readonly vramGb: number;
  // Quant's 8K-context VRAM requirement (catalog vramGb8k); used for the fits check when present.
  readonly vramGb8k?: number | null;
};

export type BenchTimeEstimate = {
  readonly lowSeconds: number;
  readonly highSeconds: number;
  readonly rough: boolean;
};

// Calibration — RTX 5090, spec 1792 GB/s (both GPUs in the board data are 1792 GB/s parts:
// RTX 5090 and RTX PRO 6000 Blackwell). Dense, non-MTP, capped-thinking runs only — the MTP
// (Qwen3.6-27B) and MoE (35B-A3B, Coder Next, Ornith) runs beat the dense-decode bound and
// cannot calibrate it:
//  A) gemma-4-12b-it__localbench-run (full five-axis, QAT Q4_K_XL, file 6,716,355,328 B):
//     6,095,115 completion tokens / 59,274 s wall = 102.8 tok/s end-to-end
//     -> implied effective bandwidth 691 GB/s -> utilization 0.39 of spec.
//  B) gemma-4-31b-it__ladder-gemma4-31b-Q4_K_M (static axes, catalog file 18.8 GB):
//     2,713,578 completion tokens / 44,836 s wall = 60.5 tok/s end-to-end
//     -> implied effective bandwidth 1138 GB/s -> utilization 0.63 of spec.
// A sits lower because its wall time includes the agentic campaign's non-decode environment
// time plus 6.2M prompt tokens of prefill. 0.5 is the geometric mean of 0.39 and 0.63 and
// reproduces A at -23% and B at +27% (both inside the ±40% calibration gate).
export const EFFECTIVE_UTILIZATION = 0.5;

// Static-suite generated tokens: 1,153 static items (129 coding + 294 instruction +
// 400 knowledge + 330 tool_calling) × ≈4,350 tok/item — the capped-thinking per-item means
// measured on the ladder runs (qwen3-6-27b Q6_K: 3,330,738/694 = 4,799; gemma-4-31b Q4_K_M:
// 2,713,578/694 = 3,910).
export const STATIC_SUITE_GENERATED_TOKENS = 5_000_000;
// Agentic overhead: the five-axis run (A) totals 6,095,115 generated tokens, i.e. the 96-task
// AppWorld campaign adds ≈1.1M tokens on top of the static portion -> ×1.22 on the suite.
export const AGENTIC_SUITE_MULTIPLIER = 1.22;
// ≈6.1M — matches run A's measured five-axis total of 6,095,115.
export const SUITE_GENERATED_TOKENS = STATIC_SUITE_GENERATED_TOKENS * AGENTIC_SUITE_MULTIPLIER;

// Verbosity spread folded into the range: run A's model spends most of its 8,192 thinking
// budget (median 8,194 tok/item) while gemma-4-31b averages 3,910 — terser and chattier
// models than the ≈4,350/item nominal both exist on the board.
const VERBOSITY_LOW = 0.7;
const VERBOSITY_HIGH = 1.5;

// Spec memory bandwidth (GB/s) of common cards per VRAM tier; EFFECTIVE_UTILIZATION converts
// spec to the end-to-end effective rate. Entries are matched by the largest minVramGb <= tier.
const TIER_BANDWIDTH_GBPS: readonly { readonly minVramGb: number; readonly low: number; readonly high: number }[] = [
  { minVramGb: 0, low: 250, high: 450 }, // 8 GB: RTX 4060 272, RX 7600 288, RTX 3060 Ti 448
  { minVramGb: 12, low: 300, high: 500 }, // 12 GB: RTX 3060 360, RX 7700 XT 432, RTX 4070 504
  { minVramGb: 16, low: 450, high: 740 }, // 16 GB: RTX 5060 Ti 448, RX 9070 XT 645, RTX 4080 717
  { minVramGb: 24, low: 600, high: 1010 }, // 24 GB: RTX 3090 936, RX 7900 XTX 960, RTX 4090 1008
  { minVramGb: 32, low: 900, high: 1800 }, // 32 GB: RTX 5090 1792 (the calibration card)
  { minVramGb: 48, low: 600, high: 900 }, // 48 GB: workstation parts — RTX A6000 768, L40S 864
  { minVramGb: 64, low: 800, high: 1800 }, // 64 GB: unified-memory desktops ~800 up to 2×5090 splits
  { minVramGb: 96, low: 1500, high: 3300 }, // 96+ GB: RTX PRO 6000 Blackwell 1792, A100 80GB 2039, H100 SXM 3350
];

// Pasted repos carry no size metadata; assume the user picked a quant sized to the tier
// (run A used 0.21× of a 32 GB card; typical 24 GB picks run 0.5-0.75×).
const PASTE_WEIGHT_FRACTION_LOW = 0.3;
const PASTE_WEIGHT_FRACTION_HIGH = 0.7;

// Q4_K_M catalog bpw — the fallback density when a quant reports paramsB but no bpw.
const DEFAULT_BPW = 4.85;

export function bandwidthRangeForTier(vramGb: number): { readonly low: number; readonly high: number } {
  let match = TIER_BANDWIDTH_GBPS[0] ?? { minVramGb: 0, low: 250, high: 450 };
  for (const entry of TIER_BANDWIDTH_GBPS) {
    if (entry.minVramGb <= vramGb) {
      match = entry;
    }
  }
  return { low: match.low, high: match.high };
}

// Physics core shared with the calibration tests: seconds to generate `generatedTokens` when
// every decoded token streams the full weights once at utilization-derated spec bandwidth.
export function decodeSeconds(generatedTokens: number, weightGb: number, bandwidthGBps: number): number {
  return (generatedTokens * weightGb) / (bandwidthGBps * EFFECTIVE_UTILIZATION);
}

function weightGbFromInput(input: BenchTimeInput): number | null {
  if (input.fileGb !== null && input.fileGb > 0) {
    return input.fileGb;
  }
  if (input.paramsB !== null && input.paramsB > 0) {
    return (input.paramsB * (input.bpw ?? DEFAULT_BPW)) / 8;
  }
  return null;
}

export function estimateBenchTime(input: BenchTimeInput): BenchTimeEstimate | null {
  const weightGb = weightGbFromInput(input);
  // Same fits rule as the picker's recommendedQuantForVram: the 8K-context requirement must be
  // inside the tier; without one, weights alone exceeding the tier is already a non-fit.
  const footprintGb = input.vramGb8k ?? weightGb;
  if (footprintGb !== null && footprintGb > input.vramGb) {
    return null;
  }
  const bandwidth = bandwidthRangeForTier(input.vramGb);
  const rough = weightGb === null;
  const weightLowGb = weightGb ?? PASTE_WEIGHT_FRACTION_LOW * input.vramGb;
  const weightHighGb = weightGb ?? PASTE_WEIGHT_FRACTION_HIGH * input.vramGb;
  return {
    lowSeconds: decodeSeconds(SUITE_GENERATED_TOKENS * VERBOSITY_LOW, weightLowGb, bandwidth.high),
    highSeconds: decodeSeconds(SUITE_GENERATED_TOKENS * VERBOSITY_HIGH, weightHighGb, bandwidth.low),
    rough,
  };
}

function roundHours(hours: number): number {
  // Half-hour steps stay readable below 10 h; whole hours above.
  return hours < 10 ? Math.max(0.5, Math.round(hours * 2) / 2) : Math.round(hours);
}

function hoursLabel(hours: number): string {
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

// Single lower-bound figure for display. The high bound assumes near-cap generation at maximum
// verbosity, which measured board runs undershoot severalfold — showing it deterred users, so the
// panel quotes the lower bound and lets the tooltip carry the caveat.
export function formatBenchTime(seconds: number): string {
  return formatBenchTimeRange(seconds, seconds);
}

export function formatBenchTimeRange(lowSeconds: number, highSeconds: number): string {
  const lo = Math.min(lowSeconds, highSeconds);
  const hi = Math.max(lowSeconds, highSeconds);
  if (hi <= 90 * 60) {
    const loMin = Math.max(5, Math.round(lo / 60 / 5) * 5);
    const hiMin = Math.max(loMin, Math.round(hi / 60 / 5) * 5);
    return loMin === hiMin ? `~${loMin} min` : `~${loMin}–${hiMin} min`;
  }
  const loHours = roundHours(lo / 3600);
  const hiHours = Math.max(loHours, roundHours(hi / 3600));
  return loHours === hiHours ? `~${hoursLabel(loHours)} h` : `~${hoursLabel(loHours)}–${hoursLabel(hiHours)} h`;
}

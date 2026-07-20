import type {
  HardwareSummary,
  Kind,
  PrimitiveRecord,
  RuntimeSummary,
  Score,
} from "./schemas";

export { axisLabel } from "./axis-config";

const SCORE_FORMAT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const COMPACT_FORMAT = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

const INTEGER_FORMAT = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const COST_FORMAT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function clampScore(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export function ciHalfWidth(score: Score): number {
  return Math.max(Math.abs(score.point - score.lo), Math.abs(score.hi - score.point));
}

export function formatScore(value: number): string {
  return SCORE_FORMAT.format(clampScore(value));
}

export function formatSignedScore(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${SCORE_FORMAT.format(Math.abs(value))}`;
}

export function displayDelta(left: number, right: number): number {
  const displayedLeft = Math.round(left * 10) / 10;
  const displayedRight = Math.round(right * 10) / 10;
  return Math.round((displayedLeft - displayedRight) * 10) / 10;
}

export function formatCi(score: Score): string {
  return `±${SCORE_FORMAT.format(ciHalfWidth(score))}`;
}

export function formatCompactNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : COMPACT_FORMAT.format(value);
}

export function formatInteger(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : INTEGER_FORMAT.format(value);
}

export function formatCost(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : COST_FORMAT.format(value);
}

export function formatGb(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${COMPACT_FORMAT.format(value)} GB`;
}

export function formatSeconds(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${COMPACT_FORMAT.format(value)}s`;
}

export function formatDuration(value: number | null | undefined): string {
  // Total wall-time to run a whole suite spans seconds to hours; show the largest sensible unit.
  if (value === null || value === undefined) {
    return "—";
  }
  if (value < 60) {
    return `${INTEGER_FORMAT.format(value)}s`;
  }
  if (value < 3600) {
    return `${INTEGER_FORMAT.format(value / 60)} min`;
  }
  return `${COMPACT_FORMAT.format(value / 3600)} h`;
}

export function formatLatencySeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (value >= 90) {
    return `~${COMPACT_FORMAT.format(value / 60)} min`;
  }
  return `~${INTEGER_FORMAT.format(value)} s`;
}

export function fallbackText(value: string | number | boolean | null | undefined): string {
  // Generated JSON uses null for unreported local/API metadata; show a placeholder, not zero.
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
}

export function formatRuntime(runtime: RuntimeSummary, kind: Kind): string {
  const name = runtime.name ?? (kind === "anchor" ? "API" : "n/a");
  const version = runtime.version ?? "n/a";
  const kv = runtime.kv_cache_quant ?? "n/a";
  const ctx = runtime.ctx_len_configured === null ? "n/a" : INTEGER_FORMAT.format(runtime.ctx_len_configured);
  return `${name} ${version} · KV ${kv} · ctx ${ctx}`;
}

export function formatGpuShort(
  gpu: { readonly name: string | null; readonly vram_gb: number | null } | null | undefined,
): string {
  // Compact GPU label for the board Hardware column: drop the "NVIDIA GeForce" noise and append
  // VRAM, e.g. "NVIDIA GeForce RTX 5090" + 32 -> "RTX 5090 · 32 GB". "—" when there is no local GPU
  // (catalog shells / API anchors).
  if (!gpu || gpu.name === null || gpu.name === "") {
    return "—";
  }
  // "NVIDIA GeForce RTX 5090" -> "RTX 5090"; "NVIDIA RTX PRO 6000" -> "RTX PRO 6000".
  const name = gpu.name.replace(/^NVIDIA\s+GeForce\s+/i, "").replace(/^NVIDIA\s+/i, "").trim();
  const vram = gpu.vram_gb === null ? "" : ` · ${INTEGER_FORMAT.format(gpu.vram_gb)} GB`;
  return `${name}${vram}`;
}

export function formatHardware(hardware: HardwareSummary): string {
  const gpu = hardware.gpu;
  const gpuName = gpu?.name ?? "n/a";
  const vram = formatGb(gpu?.vram_gb);
  const os = hardware.os ?? "n/a";
  return `${gpuName} (${vram}) · ${os}`;
}

export function formatPrimitiveRecord(record: PrimitiveRecord): string {
  const entries = Object.entries(record).map(([key, value]) => `${key}: ${fallbackText(value)}`);
  return entries.length === 0 ? "n/a" : entries.join(", ");
}

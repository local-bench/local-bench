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
  return SCORE_FORMAT.format(value);
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

export function fallbackText(value: string | number | boolean | null | undefined): string {
  // Generated JSON uses null for unreported local/API metadata; show a placeholder, not zero.
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
}

export function kindLabel(kind: Kind): string {
  switch (kind) {
    case "anchor":
      return "Anchor";
    case "community":
      return "Community-reported";
    default:
      return assertNever(kind);
  }
}

export function formatRuntime(runtime: RuntimeSummary, kind: Kind): string {
  const name = runtime.name ?? (kind === "anchor" ? "API" : "n/a");
  const version = runtime.version ?? "n/a";
  const kv = runtime.kv_cache_quant ?? "n/a";
  const ctx = runtime.ctx_len_configured === null ? "n/a" : INTEGER_FORMAT.format(runtime.ctx_len_configured);
  return `${name} ${version} · KV ${kv} · ctx ${ctx}`;
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

function assertNever(value: never): never {
  throw new Error(`Unhandled variant: ${String(value)}`);
}

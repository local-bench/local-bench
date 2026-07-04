export type VramLogDomain = {
  readonly min: number;
  readonly max: number;
};

export type VramLogScaleLayout = {
  readonly left: number;
  readonly right: number;
  readonly width: number;
};

export const VRAM_LOG_TICKS = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512] as const;
export const VRAM_LOG_LABEL_TICKS = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 512] as const;

const DEFAULT_MIN_GB = 2;
const DEFAULT_MAX_GB = 512;
const MIN_PADDING_FACTOR = 1.2;
const MAX_PADDING_FACTOR = 1.2;

export function getVramLogDomain(values: readonly number[]): VramLogDomain {
  const positive = values.filter((value) => Number.isFinite(value) && value > 0);
  if (positive.length === 0) {
    return { min: DEFAULT_MIN_GB, max: DEFAULT_MAX_GB };
  }

  const minValue = Math.min(...positive);
  const maxValue = Math.max(...positive);
  const min = Math.min(DEFAULT_MIN_GB, Math.max(0.25, minValue / MIN_PADDING_FACTOR));
  const max = snapUpVramTier(Math.max(DEFAULT_MAX_GB, maxValue * MAX_PADDING_FACTOR));
  return { min, max };
}

export function scaleVramLogX(value: number, domain: VramLogDomain, layout: VramLogScaleLayout): number {
  const plotWidth = layout.width - layout.left - layout.right;
  const lo = Math.log2(domain.min);
  const hi = Math.log2(domain.max);
  const span = hi - lo || 1;
  const clamped = Math.max(value, domain.min);
  return layout.left + ((Math.log2(clamped) - lo) / span) * plotWidth;
}

function snapUpVramTier(value: number): number {
  return VRAM_LOG_TICKS.find((tier) => tier >= value) ?? 2 ** Math.ceil(Math.log2(value));
}

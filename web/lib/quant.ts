export const QUANT_OPTIONS = ["FP16", "Q8_0", "Q5_K_M", "Q4_K_M", "Q3_K_M"] as const;

export type QuantOption = (typeof QUANT_OPTIONS)[number];
export type QuantFilter = "any" | QuantOption;

export const QUANT_BYTES_PER_PARAM = {
  FP16: 2,
  Q8_0: 1,
  Q5_K_M: 0.625,
  Q4_K_M: 0.5,
  Q3_K_M: 0.375,
} as const satisfies Record<QuantOption, number>;

const DEFAULT_QUANT_BYTES_PER_PARAM = 1;
const UNKNOWN_QUANT_RANK = 5;
const NULL_QUANT_RANK = 6;

const QUANT_ORDER = {
  FP16: 0,
  Q8_0: 1,
  Q5_K_M: 2,
  Q4_K_M: 3,
  Q3_K_M: 4,
} as const satisfies Record<QuantOption, number>;

export function isQuantOption(value: string | null): value is QuantOption {
  switch (value) {
    case "FP16":
    case "Q8_0":
    case "Q5_K_M":
    case "Q4_K_M":
    case "Q3_K_M":
      return true;
    case null:
    default:
      return false;
  }
}

export function toQuantFilter(value: string): QuantFilter {
  return isQuantOption(value) ? value : "any";
}

export function quantBytesPerParam(quantLabel: string | null): number {
  return isQuantOption(quantLabel) ? QUANT_BYTES_PER_PARAM[quantLabel] : DEFAULT_QUANT_BYTES_PER_PARAM;
}

export function quantOrder(quantLabel: QuantOption): number {
  return QUANT_ORDER[quantLabel];
}

export function quantRank(quantLabel: string | null): number {
  if (quantLabel === null) {
    return NULL_QUANT_RANK;
  }
  return isQuantOption(quantLabel) ? quantOrder(quantLabel) : UNKNOWN_QUANT_RANK;
}

import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  findMinimumVramTier,
  type ContextLengthOption,
  type VramEstimate,
} from "./rig-match";
import { QUANT_OPTIONS, isQuantOption, quantOrder } from "./quant";
import type { QuantOption } from "./quant";
import type { Score } from "./schemas";

const SWEET_SPOT_MIN_BASELINE_RETENTION = 0.95;

export type QuantDecisionInputRun = {
  readonly composite: Score;
  readonly demo: boolean;
  readonly quant_label: string | null;
  readonly run_id: string;
  readonly tok_s: number | null;
  readonly vram_footprint_gb: number | null;
};

export type QuantDecisionInputModel = {
  readonly model_label: string;
  readonly runs: readonly QuantDecisionInputRun[];
  readonly slug: string;
};

export type QuantDecisionRow = {
  readonly deltaVsBaseline: Score | null;
  readonly fitTierGb: number | null;
  readonly isBaseline: boolean;
  readonly isSweetSpot: boolean;
  readonly quantLabel: QuantOption;
  readonly run: QuantDecisionInputRun | null;
  readonly vramEstimate: VramEstimate | null;
};

export type QuantDecisionRows = {
  readonly baselineQuantLabel: QuantOption | null;
  readonly hasFp16Baseline: boolean;
  readonly missingQuantLabels: readonly QuantOption[];
  readonly rows: readonly QuantDecisionRow[];
};

export function getQuantDecisionRows(
  model: QuantDecisionInputModel,
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): QuantDecisionRows {
  const runsByQuant = bestRunsByQuant(model.runs);
  const fp16Baseline = runsByQuant.get("FP16") ?? null;
  const baselineQuantLabel = fp16Baseline === null ? firstMeasuredQuant(runsByQuant) : "FP16";
  const baseline = baselineQuantLabel === null ? null : runsByQuant.get(baselineQuantLabel) ?? null;
  const rows = QUANT_OPTIONS.map((quantLabel) =>
    toDecisionRow(quantLabel, runsByQuant.get(quantLabel) ?? null, baselineQuantLabel, baseline, contextTokens),
  );
  const sweetSpotQuant = chooseSweetSpot(rows, baseline);

  return {
    baselineQuantLabel,
    hasFp16Baseline: fp16Baseline !== null,
    missingQuantLabels: rows.filter((row) => row.run === null).map((row) => row.quantLabel),
    rows: rows.map((row) => ({ ...row, isSweetSpot: row.quantLabel === sweetSpotQuant })),
  };
}

function bestRunsByQuant(runs: readonly QuantDecisionInputRun[]): ReadonlyMap<QuantOption, QuantDecisionInputRun> {
  const bestRuns = new Map<QuantOption, QuantDecisionInputRun>();
  for (const run of runs) {
    if (!isQuantOption(run.quant_label)) {
      continue;
    }
    const current = bestRuns.get(run.quant_label);
    if (current === undefined || isBetterRun(run, current)) {
      bestRuns.set(run.quant_label, run);
    }
  }
  return bestRuns;
}

function toDecisionRow(
  quantLabel: QuantOption,
  run: QuantDecisionInputRun | null,
  baselineQuantLabel: QuantOption | null,
  baseline: QuantDecisionInputRun | null,
  contextTokens: ContextLengthOption,
): QuantDecisionRow {
  const vramEstimate = run === null ? null : estimateVramRequirement({ quantLabel, vramFootprintGb: run.vram_footprint_gb }, contextTokens);
  return {
    deltaVsBaseline: run === null || baseline === null ? null : deltaScore(run.composite, baseline.composite),
    fitTierGb: vramEstimate === null ? null : findMinimumVramTier(vramEstimate.effectiveRequiredGb),
    isBaseline: quantLabel === baselineQuantLabel && run !== null,
    isSweetSpot: false,
    quantLabel,
    run,
    vramEstimate,
  };
}

function firstMeasuredQuant(runsByQuant: ReadonlyMap<QuantOption, QuantDecisionInputRun>): QuantOption | null {
  return QUANT_OPTIONS.find((quantLabel) => runsByQuant.has(quantLabel)) ?? null;
}

function chooseSweetSpot(rows: readonly QuantDecisionRow[], baseline: QuantDecisionInputRun | null): QuantOption | null {
  if (baseline === null || baseline.composite.point <= 0) {
    return null;
  }

  const candidates = rows
    .filter((row) => row.run !== null && !row.isBaseline && row.vramEstimate !== null)
    .filter((row) => qualityRetention(row, baseline) >= SWEET_SPOT_MIN_BASELINE_RETENTION);
  const best = [...candidates].sort(compareSweetSpotRows)[0];
  return best?.quantLabel ?? null;
}

function qualityRetention(row: QuantDecisionRow, baseline: QuantDecisionInputRun): number {
  return row.run === null ? 0 : row.run.composite.point / baseline.composite.point;
}

function compareSweetSpotRows(left: QuantDecisionRow, right: QuantDecisionRow): number {
  return (
    nullableNumber(left.vramEstimate?.effectiveRequiredGb, Number.POSITIVE_INFINITY) -
      nullableNumber(right.vramEstimate?.effectiveRequiredGb, Number.POSITIVE_INFINITY) ||
    nullableNumber(right.run?.composite.point, Number.NEGATIVE_INFINITY) -
      nullableNumber(left.run?.composite.point, Number.NEGATIVE_INFINITY) ||
    quantOrder(left.quantLabel) - quantOrder(right.quantLabel)
  );
}

function isBetterRun(candidate: QuantDecisionInputRun, current: QuantDecisionInputRun): boolean {
  const scoreDelta = candidate.composite.point - current.composite.point;
  if (scoreDelta !== 0) {
    return scoreDelta > 0;
  }
  return (
    nullableNumber(candidate.vram_footprint_gb, Number.POSITIVE_INFINITY) <
    nullableNumber(current.vram_footprint_gb, Number.POSITIVE_INFINITY)
  );
}

function deltaScore(runScore: Score, baselineScore: Score): Score {
  return {
    hi: runScore.hi - baselineScore.lo,
    lo: runScore.lo - baselineScore.hi,
    point: runScore.point - baselineScore.point,
  };
}

function nullableNumber(value: number | null | undefined, fallback: number): number {
  return value ?? fallback;
}

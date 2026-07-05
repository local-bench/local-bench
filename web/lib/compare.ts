import { AXIS_KEYS, type AxisKey } from "./axis-config";
import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  findMinimumVramTier,
  type ContextLengthOption,
  type VramEstimate,
} from "./rig-match";
import type { AxisScore, ModelData, Score } from "./schemas";

export type CompareCoverage = "full" | "partial";

export type CompareConfig = {
  readonly axes: Record<string, AxisScore>;
  readonly composite: Score;
  readonly coverage: CompareCoverage;
  readonly demo: boolean;
  readonly fitTierGb: number | null;
  readonly id: string;
  readonly modelLabel: string;
  readonly modelSlug: string;
  readonly quantLabel: string;
  readonly runId: string;
  readonly tokS: number | null;
  readonly vramEstimate: VramEstimate | null;
};

const HEADLINE_AXIS_KEYS = ["agentic", "knowledge", "instruction", "tool_calling", "coding"] as const;

export type AxisDelta = {
  readonly axis: AxisKey;
  readonly delta: number;
  readonly leftScore: AxisScore;
  readonly rightScore: AxisScore;
  readonly winner: "left" | "right" | "tie";
};

export function getCompareConfigs(
  models: readonly ModelData[],
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): readonly CompareConfig[] {
  return models
    .filter((model) => model.kind === "community")
    .flatMap((model) =>
      model.runs.flatMap((run) => {
        if (!isNonEmptyString(run.quant_label) || run.composite === null || run.run_id === null) {
          return [];
        }
        const vramEstimate = estimateVramRequirement(
          {
            quantLabel: run.quant_label,
            vramFootprintGb: run.vram_footprint_gb,
            vramRequiredGb8k: run.vram_required_gb_8k ?? null,
          },
          contextTokens,
        );
        return [
          {
            axes: run.axes,
            composite: run.composite,
            coverage: coverageForAxes(run.axes),
            demo: model.demo || run.demo,
            fitTierGb: vramEstimate === null ? null : findMinimumVramTier(vramEstimate.effectiveRequiredGb),
            id: run.run_id,
            modelLabel: model.model_label,
            modelSlug: model.slug,
            quantLabel: run.quant_label,
            runId: run.run_id,
            tokS: run.tok_s,
            vramEstimate,
          },
        ];
      }),
    )
    .sort(compareConfigs);
}

export function getAxisDeltas(left: CompareConfig, right: CompareConfig): readonly AxisDelta[] {
  return AXIS_KEYS.flatMap((axis) => {
    const leftScore = left.axes[axis];
    const rightScore = right.axes[axis];
    if (leftScore === undefined || rightScore === undefined) {
      return [];
    }
    const delta = leftScore.point - rightScore.point;
    return [{ axis, delta, leftScore, rightScore, winner: winnerFor(delta) }];
  });
}

function coverageForAxes(axes: Readonly<Record<string, AxisScore>>): CompareCoverage {
  return HEADLINE_AXIS_KEYS.every((axis) => axes[axis] !== undefined) ? "full" : "partial";
}

function isNonEmptyString(value: string | null): value is string {
  return value !== null && value.trim() !== "";
}

function compareConfigs(left: CompareConfig, right: CompareConfig): number {
  return (
    right.composite.point - left.composite.point ||
    left.modelLabel.localeCompare(right.modelLabel) ||
    left.quantLabel.localeCompare(right.quantLabel)
  );
}

function winnerFor(delta: number): "left" | "right" | "tie" {
  if (Math.abs(delta) < 0.05) {
    return "tie";
  }
  return delta > 0 ? "left" : "right";
}

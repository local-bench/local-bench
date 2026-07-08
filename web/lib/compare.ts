import { AXIS_KEYS, type AxisKey } from "./axis-config";
import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  findMinimumVramTier,
  type ContextLengthOption,
  type VramEstimate,
} from "./rig-match";
import { HEADLINE_LANE } from "./leaderboard-score";
import type { AxisScore, ModelData, Score } from "./schemas";

export type CompareCoverage = "full" | "partial";
export type CompareScoreScope = "current-index" | "previous-index";

export type CompareConfig = {
  readonly axes: Record<string, AxisScore>;
  readonly composite: Score;
  readonly coverage: CompareCoverage;
  readonly demo: boolean;
  readonly fitTierGb: number | null;
  readonly id: string;
  readonly lane: string | null;
  readonly modelLabel: string;
  readonly modelSlug: string;
  readonly quantLabel: string;
  readonly runId: string;
  readonly scoreScope: CompareScoreScope;
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
        const score = scoreForRun(run);
        if (!isNonEmptyString(run.quant_label) || score === null || run.run_id === null) {
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
            composite: score,
            coverage: coverageForAxes(run.axes),
            demo: model.demo || run.demo,
            fitTierGb: vramEstimate === null ? null : findMinimumVramTier(vramEstimate.effectiveRequiredGb),
            id: run.run_id,
            lane: run.lane,
            modelLabel: model.model_label,
            modelSlug: model.slug,
            quantLabel: run.quant_label,
            runId: run.run_id,
            scoreScope: scoreScopeForLane(run.lane),
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
    scopeRank(left) - scopeRank(right) ||
    right.composite.point - left.composite.point ||
    left.modelLabel.localeCompare(right.modelLabel) ||
    left.quantLabel.localeCompare(right.quantLabel)
  );
}

function scopeRank(config: CompareConfig): number {
  return config.scoreScope === "current-index" ? 0 : 1;
}

function scoreScopeForLane(lane: string | null): CompareScoreScope {
  return lane === HEADLINE_LANE ? "current-index" : "previous-index";
}

function scoreForRun(run: ModelData["runs"][number]): Score | null {
  if (run.lane === HEADLINE_LANE) {
    return run.composite;
  }
  return run.diagnostic_composite ?? run.composite;
}

function winnerFor(delta: number): "left" | "right" | "tie" {
  if (Math.abs(delta) < 0.05) {
    return "tie";
  }
  return delta > 0 ? "left" : "right";
}

import { AXIS_KEYS, type AxisKey } from "./axis-config";
import { toDisplayScore } from "./board-adapter";
import {
  DEFAULT_CONTEXT_TOKENS,
  findMinimumVramTier,
  type ContextLengthOption,
  type VramEstimate,
} from "./rig-match";
import { HEADLINE_LANE } from "./leaderboard-score";
import { displayDelta } from "./format";
import { estimateRunVram } from "./model-run-metrics";
import type { AxisScore, ModelData, Score } from "./schemas";
import type { CommunityBoardRow } from "./community-data";
import { SEASON_2_HEADLINE_AXES } from "./scoring-seasons";
import { isTrustedPopulation } from "./trusted-population";

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
  readonly modelHref: string | null;
  readonly modelSlug: string;
  readonly quantLabel: string;
  readonly runId: string;
  readonly scoreScope: CompareScoreScope;
  readonly tokS: number | null;
  readonly vramEstimate: VramEstimate | null;
};

const HEADLINE_AXIS_KEYS = ["agentic", "knowledge", "instruction", "tool_calling", "coding"] as const;

export type AxisDelta = {
  readonly axis: AxisKey | "tool_use";
  readonly delta: number;
  readonly leftScore: AxisScore;
  readonly rightScore: AxisScore;
  readonly winner: "left" | "right" | "tie";
};

export function getCompareConfigs(
  models: readonly ModelData[],
  communityRows: readonly CommunityBoardRow[] = [],
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): readonly CompareConfig[] {
  const stored = models
    .filter((model) => model.kind === "community")
    .flatMap((model) =>
      model.runs.flatMap((run) => {
        if (!isTrustedPopulation(run)) return [];
        const score = scoreForRun(run);
        if (!isNonEmptyString(run.quant_label) || score === null || run.run_id === null) {
          return [];
        }
        const vramEstimate = estimateRunVram(run, model.runs, contextTokens);
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
            modelHref: `/model/${model.slug}`,
            modelSlug: model.slug,
            quantLabel: run.quant_label,
            runId: run.run_id,
            scoreScope: scoreScopeForLane(run.lane),
            tokS: run.tok_s,
            vramEstimate,
          },
        ];
      }),
    );
  const community = communityRows.flatMap((row): readonly CompareConfig[] => {
    if (!row.headlineComplete || row.compositeFull === null || !isNonEmptyString(row.quantLabel)) return [];
    const axes = communityAxes(row);
    const point = toDisplayScore(row.compositeFull);
    const modelSlug = row.detailPath?.replace(/^\/model\//u, "") ?? "";
    return [{
      axes,
      composite: { hi: point, lo: point, point },
      coverage: "full",
      demo: false,
      fitTierGb: null,
      id: row.submissionId,
      lane: HEADLINE_LANE,
      modelLabel: row.displayName,
      modelHref: row.detailPath,
      modelSlug,
      quantLabel: row.quantLabel,
      runId: row.submissionId,
      scoreScope: "current-index",
      tokS: null,
      vramEstimate: null,
    }];
  });
  return [...stored, ...community].sort(compareConfigs);
}

export function getAxisDeltas(left: CompareConfig, right: CompareConfig): readonly AxisDelta[] {
  const axes = left.axes["tool_use"] !== undefined || right.axes["tool_use"] !== undefined
    ? SEASON_2_HEADLINE_AXES
    : AXIS_KEYS;
  return axes.flatMap((axis) => {
    const leftScore = left.axes[axis];
    const rightScore = right.axes[axis];
    if (leftScore === undefined || rightScore === undefined) {
      return [];
    }
    const delta = displayDelta(leftScore.point, rightScore.point);
    return [{ axis, delta, leftScore, rightScore, winner: winnerFor(delta) }];
  });
}

function coverageForAxes(axes: Readonly<Record<string, AxisScore>>): CompareCoverage {
  const required = axes["tool_use"] === undefined ? HEADLINE_AXIS_KEYS : SEASON_2_HEADLINE_AXES;
  return required.every((axis) => axes[axis] !== undefined) ? "full" : "partial";
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

function communityAxes(row: CommunityBoardRow): Record<string, AxisScore> {
  return Object.fromEntries(Object.entries(row.axes ?? {}).flatMap(([key, axis]) => {
    if (axis.status !== "measured" || axis.score === null || axis.score === undefined) return [];
    const point = toDisplayScore(axis.score);
    const lo = axis.ci?.[0] === undefined ? point : toDisplayScore(axis.ci[0]);
    const hi = axis.ci?.[1] === undefined ? point : toDisplayScore(axis.ci[1]);
    return [[key, {
      hi,
      lo,
      n: axis.n,
      n_errors: 0,
      n_no_answer: 0,
      point,
      raw_accuracy: axis.score <= 1 ? axis.score : axis.score / 100,
    }]];
  }));
}

import { type AxisKey } from "@/lib/axis-config";
import {
  contributionTotal,
  indexContributionTitle,
  indexContributions,
  type IndexContribution,
} from "@/lib/axis-contributions";
import { clampScore, formatScore } from "@/lib/format";
import { scoreForMode } from "@/lib/leaderboard-score";
import type { IndexModel, Score } from "@/lib/schemas";

export const PLOT = {
  bottom: 28,
  left: 42,
  right: 18,
  top: 32,
} as const;
export const SVG_HEIGHT = 300;
const PLOT_HEIGHT = SVG_HEIGHT - PLOT.top - PLOT.bottom;
export const SLOT_WIDTH = 88;
export const BAR_WIDTH = 40;
export const TICKS = [0, 20, 40, 60, 80, 100] as const;

type ScoredModel = {
  readonly model: IndexModel;
  readonly score: Score;
};

type StackSegment = {
  readonly key: AxisKey | "unallocated";
  readonly label: string;
  readonly color: string;
  readonly muted: boolean;
  readonly value: number;
};

type RenderedSegment = StackSegment & {
  readonly height: number;
  readonly y: number;
};

export type ChartRow = ScoredModel & {
  readonly barCenter: number;
  readonly barLeft: number;
  readonly barTop: number;
  readonly contributions: readonly IndexContribution[];
  readonly labelCenter: number;
  readonly missingLabels: readonly string[];
  readonly renderedSegments: readonly RenderedSegment[];
  readonly scorePoint: number;
  readonly tooltipLines: readonly string[];
};

export function toChartRows(models: readonly IndexModel[]): readonly ChartRow[] {
  return models.map(toScoredModel).filter(isScoredModel).sort(compareScoredModels).map(toChartRow);
}

function toScoredModel(model: IndexModel): ScoredModel | null {
  const score = scoreForMode(model, "full");
  return score === null ? null : { model, score };
}

function isScoredModel(row: ScoredModel | null): row is ScoredModel {
  return row !== null;
}

function compareScoredModels(left: ScoredModel, right: ScoredModel): number {
  return right.score.point - left.score.point || left.model.model_label.localeCompare(right.model.model_label);
}

function toChartRow(input: ScoredModel, index: number): ChartRow {
  const contributions = indexContributions(input.model.axes);
  const missingLabels = contributions
    .filter((contribution) => input.model.axes[contribution.key] === undefined)
    .map((contribution) => contribution.label);
  const scorePoint = sanitizeScaleInput(input.score.point);
  const barCenter = PLOT.left + index * SLOT_WIDTH + SLOT_WIDTH / 2;
  const renderedSegments = toRenderedSegments(toStackSegments({ contributions, missingLabels, scorePoint }));
  const barTop = scaleY(scorePoint);
  return {
    ...input,
    barCenter,
    barLeft: barCenter - BAR_WIDTH / 2,
    barTop,
    contributions,
    labelCenter: barCenter,
    missingLabels,
    renderedSegments,
    scorePoint,
    tooltipLines: tooltipLines({
      contributions,
      missingLabels,
      modelLabel: input.model.model_label,
      score: input.score,
      segments: renderedSegments,
    }),
  };
}

function toStackSegments(input: {
  readonly contributions: readonly IndexContribution[];
  readonly missingLabels: readonly string[];
  readonly scorePoint: number;
}): readonly StackSegment[] {
  const total = contributionTotal(input.contributions);
  if (total <= 0) {
    return [];
  }
  const scale = input.missingLabels.length === 0 ? input.scorePoint / total : 1;
  const measured = input.contributions
    .filter((contribution) => contribution.contribution > 0)
    .map((contribution) => ({
      key: contribution.key,
      label: contribution.label,
      color: contribution.color,
      muted: false,
      value: contribution.contribution * scale,
    }));
  const measuredTotal = measured.reduce((sum, segment) => sum + segment.value, 0);
  const unallocated = input.missingLabels.length === 0 ? 0 : Math.max(0, input.scorePoint - measuredTotal);
  return unallocated > 0
    ? [
        ...measured,
        {
          key: "unallocated",
          label: "Unallocated",
          color: "",
          muted: true,
          value: unallocated,
        },
      ]
    : measured;
}

function toRenderedSegments(segments: readonly StackSegment[]): readonly RenderedSegment[] {
  let cumulative = 0;
  return segments
    .map((segment) => {
      const bottom = sanitizeScaleInput(cumulative);
      cumulative += segment.value;
      const top = sanitizeScaleInput(cumulative);
      return {
        ...segment,
        height: roundForAttribute(scaleY(bottom) - scaleY(top)),
        y: roundForAttribute(scaleY(top)),
      };
    })
    .filter((segment) => segment.height > 0);
}

function tooltipLines(input: {
  readonly contributions: readonly IndexContribution[];
  readonly missingLabels: readonly string[];
  readonly modelLabel: string;
  readonly score: Score;
  readonly segments: readonly StackSegment[];
}): readonly string[] {
  const unallocated = input.segments.find((segment) => segment.key === "unallocated");
  // The uncertainty range lives here in the tooltip now that the chart no longer draws
  // whiskers (owner call 2026-07-09).
  const base = `${input.modelLabel} — ${formatScore(input.score.point)} (${formatScore(input.score.lo)}–${formatScore(
    input.score.hi,
  )})`;
  if (input.missingLabels.length === 0) {
    return [base, indexContributionTitle(input.contributions)];
  }
  return [
    base,
    `${indexContributionTitle(input.contributions)}; Unallocated ${(unallocated?.value ?? 0).toFixed(1)}`,
    `Missing: ${input.missingLabels.join(", ")}`,
  ];
}

function sanitizeScaleInput(value: number): number {
  return Number.isFinite(value) ? clampScore(value) : 0;
}

export function scaleY(value: number): number {
  return PLOT.top + (1 - sanitizeScaleInput(value) / 100) * PLOT_HEIGHT;
}

export function roundForAttribute(value: number): number {
  return Number(value.toFixed(3));
}

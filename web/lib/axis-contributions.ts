import { AXIS_CONFIG, type AxisKey } from "./axis-config";
import type { AxisScore } from "./schemas";

export const INDEX_AXIS_WEIGHTS = {
  agentic: 0.4,
  knowledge: 0.15,
  instruction: 0.15,
  tool_calling: 0.1,
  coding: 0.15,
  math: 0.05,
} as const satisfies Readonly<Record<AxisKey, number>>;

export type IndexContribution = {
  readonly key: AxisKey;
  readonly label: string;
  readonly color: string;
  readonly contribution: number;
};

const TITLE_LABELS = {
  agentic: "Agentic",
  knowledge: "Knowledge",
  instruction: "Instruction",
  tool_calling: "Tool",
  coding: "Coding",
  math: "Math",
} as const satisfies Readonly<Record<AxisKey, string>>;

export function indexContributions(axes: Readonly<Record<string, AxisScore>>): readonly IndexContribution[] {
  return AXIS_CONFIG.map((axis) => ({
    key: axis.key,
    label: axis.label,
    color: axis.color,
    contribution: weightedPoint(axes[axis.key], INDEX_AXIS_WEIGHTS[axis.key]),
  }));
}

export function contributionTotal(contributions: readonly Pick<IndexContribution, "contribution">[]): number {
  return contributions.reduce((total, contribution) => total + contribution.contribution, 0);
}

export function indexContributionTitle(contributions: readonly IndexContribution[]): string {
  const parts = contributions.map(
    (contribution) => `${TITLE_LABELS[contribution.key]} ${contribution.contribution.toFixed(1)}`,
  );
  return `${parts.join(" + ")} = ${contributionTotal(contributions).toFixed(1)}`;
}

function weightedPoint(score: AxisScore | undefined, weight: number): number {
  const point = score?.point ?? 0;
  return Number.isFinite(point) && point > 0 ? point * weight : 0;
}

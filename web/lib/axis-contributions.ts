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

export const SEASON_2_AXIS_WEIGHTS = {
  knowledge: 0.24,
  instruction: 0.24,
  tool_use: 0.2,
  coding: 0.24,
  math: 0.08,
} as const;

export type IndexContribution = {
  readonly key: AxisKey | "tool_use";
  readonly label: string;
  readonly color: string;
  readonly contribution: number;
};

const TITLE_LABELS: Readonly<Record<string, string>> = {
  agentic: "Agentic",
  knowledge: "Knowledge",
  instruction: "Instruction",
  tool_use: "Tool use",
  tool_calling: "Tool",
  coding: "Coding",
  math: "Math",
};

export function indexContributions(axes: Readonly<Record<string, AxisScore>>): readonly IndexContribution[] {
  const season2 = axes["tool_use"] !== undefined;
  const weights: Readonly<Record<string, number>> = season2 ? SEASON_2_AXIS_WEIGHTS : INDEX_AXIS_WEIGHTS;
  const config: readonly { readonly key: AxisKey | "tool_use"; readonly label: string; readonly color: string }[] = season2
    ? [
        { key: "tool_use", label: "Tool use", color: "#ffb627" },
        ...AXIS_CONFIG.filter((axis) => ["knowledge", "instruction", "coding", "math"].includes(axis.key)),
      ]
    : AXIS_CONFIG;
  return config.map((axis) => ({
    key: axis.key,
    label: axis.label,
    color: axis.color,
    contribution: weightedPoint(axes[axis.key], weights[axis.key] ?? 0),
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

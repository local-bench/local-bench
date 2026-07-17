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

// index-v4.1 weights — MUST match cli/src/localbench/scoring/axes.py AXES.
// Agentic macro-axis (key tool_use) 0.25; the other four = old values x 15/16.
export const SEASON_2_AXIS_WEIGHTS = {
  knowledge: 0.225,
  instruction: 0.225,
  tool_use: 0.25,
  coding: 0.225,
  math: 0.075,
} as const;

export type IndexContribution = {
  readonly key: AxisKey | "tool_use";
  readonly label: string;
  readonly color: string;
  readonly contribution: number;
};

const TITLE_LABELS: Readonly<Record<string, string>> = {
  // "agentic" is the season-1 AppWorld-only axis; "tool_use" is the season-2
  // Agentic macro-axis. Same display word, but the two never share a view:
  // contribution rails branch on season, and mixed-season rails are forbidden.
  agentic: "Agentic",
  knowledge: "Knowledge",
  instruction: "Instruction",
  tool_use: "Agentic",
  tool_calling: "Tool",
  coding: "Coding",
  math: "Math",
};

export function indexContributions(axes: Readonly<Record<string, AxisScore>>): readonly IndexContribution[] {
  const season2 = axes["tool_use"] !== undefined;
  const weights: Readonly<Record<string, number>> = season2 ? SEASON_2_AXIS_WEIGHTS : INDEX_AXIS_WEIGHTS;
  const config: readonly { readonly key: AxisKey | "tool_use"; readonly label: string; readonly color: string }[] = season2
    ? [
        { key: "tool_use", label: "Agentic", color: "#ffb627" },
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

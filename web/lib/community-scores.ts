import { boardAxisValue, toDisplayScore } from "./board-adapter";
import type { CommunityBoardRow } from "./community-data";
import { INDEX_VERSION_V3 } from "./scoring-seasons";
import type { AxisScore, Score } from "./schemas";

export type CommunityScore = Score & { readonly hasConfidenceInterval: boolean };
export type CommunityAxisScore = AxisScore & { readonly hasConfidenceInterval: boolean };

export function communityScore(value: number): CommunityScore {
  const point = toDisplayScore(value);
  return { point, lo: point, hi: point, hasConfidenceInterval: false };
}

export function communityAxisScore(
  value: NonNullable<CommunityBoardRow["axes"]>[string] | undefined,
): CommunityAxisScore | undefined {
  if (value === undefined || value.status !== "measured" || value.score === null || value.score === undefined || value.n === 0) {
    return undefined;
  }
  const point = toDisplayScore(value.score);
  const hasConfidenceInterval = value.ci !== null;
  const lo = toDisplayScore(value.ci?.[0] ?? value.score);
  const hi = toDisplayScore(value.ci?.[1] ?? value.score);
  return {
    point,
    lo,
    hi,
    raw_accuracy: value.score <= 1 ? value.score : value.score / 100,
    n: value.n,
    n_errors: 0,
    n_no_answer: 0,
    hasConfidenceInterval,
  };
}

export function communityDisplayAxes(row: CommunityBoardRow): Record<string, AxisScore> {
  const axes = row.axes ?? {};
  const keys = communityUsesLegacyAxes(row)
    ? ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"]
    : ["tool_use", "knowledge", "instruction", "coding", "math"];
  return Object.fromEntries(keys.flatMap((key) => {
    const score = communityAxisScore(boardAxisValue(axes, key));
    return score === undefined ? [] : [[key, score]];
  }));
}

export function communityUsesLegacyAxes(row: CommunityBoardRow): boolean {
  if (row.indexVersion === INDEX_VERSION_V3) return true;
  if (row.indexVersion !== null) return false;
  return row.axes?.["tool_calling"] !== undefined;
}

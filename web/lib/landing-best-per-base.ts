import {
  familyResolutionKey,
  resolveFamily,
  type FamilyResolution,
  type FamilyResolutionContext,
} from "./family-resolution";
import { isFullIndexRow, scoreForMode } from "./leaderboard-score";
import type { IndexModel } from "./schemas";

export type FamilyRankedSource = "community" | "maintainer";

export type BestPerFamilyCandidate<T> = {
  readonly displayedComposite: number;
  readonly familyKey?: string;
  readonly resolution: FamilyResolution;
  readonly source: FamilyRankedSource;
  readonly value: T;
};

export function selectBestPerFamily<T>(
  candidates: readonly BestPerFamilyCandidate<T>[],
): readonly BestPerFamilyCandidate<T>[] {
  const winnerByFamily = new Map<string, number>();
  for (const [index, candidate] of candidates.entries()) {
    const key = candidateFamilyKey(candidate);
    if (key === null) continue;
    const incumbentIndex = winnerByFamily.get(key);
    if (incumbentIndex === undefined) {
      winnerByFamily.set(key, index);
      continue;
    }
    const incumbent = candidates[incumbentIndex];
    if (incumbent !== undefined && isBetterCandidate(candidate, incumbent)) {
      winnerByFamily.set(key, index);
    }
  }
  return candidates.filter((candidate, index) => {
    const key = candidateFamilyKey(candidate);
    return key === null || winnerByFamily.get(key) === index;
  });
}

function candidateFamilyKey<T>(candidate: BestPerFamilyCandidate<T>): string | null {
  return candidate.familyKey ?? familyResolutionKey(candidate.resolution);
}

export function selectLandingBestPerBase(
  models: readonly IndexModel[],
  context: FamilyResolutionContext,
): readonly IndexModel[] {
  const candidates = models.flatMap((model) => {
    if (!isFullIndexRow(model)) return [];
    const score = scoreForMode(model, "full");
    if (score === null) return [];
    return [{
      displayedComposite: score.point,
      resolution: resolveFamily(model, context),
      source: "maintainer" as const,
      value: model,
    }];
  });
  return selectBestPerFamily(candidates).map((candidate) => candidate.value);
}

function isBetterCandidate<T>(
  candidate: BestPerFamilyCandidate<T>,
  incumbent: BestPerFamilyCandidate<T>,
): boolean {
  if (candidate.displayedComposite !== incumbent.displayedComposite) {
    return candidate.displayedComposite > incumbent.displayedComposite;
  }
  return candidate.source === "maintainer" && incumbent.source === "community";
}

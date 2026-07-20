import { compareFamilyNames, familyRoutes } from "./family-slug";
import { isFullIndexRow, scoreForMode } from "./leaderboard-score";
import type { IndexModel } from "./schemas";

export type FamilyModelSummary = {
  readonly model: IndexModel;
  readonly score: number | null;
};

export type FamilySummary = {
  readonly bestScore: number | null;
  readonly family: string;
  readonly models: readonly FamilyModelSummary[];
  readonly slug: string;
};

export function familySummaries(models: readonly IndexModel[]): readonly FamilySummary[] {
  const byFamily = new Map<string, IndexModel[]>();
  for (const model of models) byFamily.set(model.family, [...(byFamily.get(model.family) ?? []), model]);
  return familyRoutes([...byFamily.keys()])
    .flatMap(({ family, slug }) => {
      const familyModels = byFamily.get(family);
      if (familyModels === undefined) return [];
      const orderedModels = familyModels.map(toFamilyModelSummary).sort(compareFamilyModels);
      return [{
        bestScore: orderedModels.find((entry) => entry.score !== null)?.score ?? null,
        family,
        models: orderedModels,
        slug,
      }];
    })
    .sort(compareFamilies);
}

function toFamilyModelSummary(model: IndexModel): FamilyModelSummary {
  return {
    model,
    score: isFullIndexRow(model) ? scoreForMode(model, "full")?.point ?? null : null,
  };
}

function compareFamilyModels(left: FamilyModelSummary, right: FamilyModelSummary): number {
  if (left.score !== null && right.score !== null) {
    return right.score - left.score || compareFamilyNames(left.model.model_label, right.model.model_label);
  }
  if (left.score !== null) return -1;
  if (right.score !== null) return 1;
  return compareFamilyNames(left.model.model_label, right.model.model_label);
}

function compareFamilies(left: FamilySummary, right: FamilySummary): number {
  if (left.bestScore !== null && right.bestScore !== null) {
    return right.bestScore - left.bestScore || compareFamilyNames(left.family, right.family);
  }
  if (left.bestScore !== null) return -1;
  if (right.bestScore !== null) return 1;
  return compareFamilyNames(left.family, right.family);
}

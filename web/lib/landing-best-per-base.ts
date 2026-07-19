import { isFullIndexRow } from "./leaderboard-score";
import type { IndexModel } from "./schemas";

export function selectLandingBestPerBase(
  models: readonly IndexModel[],
  fineTuneBaseBySlug: ReadonlyMap<string, string>,
): readonly IndexModel[] {
  const bestByBase = new Map<string, IndexModel>();
  for (const model of models) {
    if (!isFullIndexRow(model)) continue;
    const baseIdentity = fineTuneBaseBySlug.get(model.slug) ?? model.model_label;
    const best = bestByBase.get(baseIdentity);
    if ((model.composite_full?.point ?? Number.NEGATIVE_INFINITY)
      > (best?.composite_full?.point ?? Number.NEGATIVE_INFINITY)) {
      bestByBase.set(baseIdentity, model);
    }
  }
  return models.filter((model) => {
    if (!isFullIndexRow(model)) return true;
    const baseIdentity = fineTuneBaseBySlug.get(model.slug) ?? model.model_label;
    return bestByBase.get(baseIdentity)?.slug === model.slug;
  });
}

import type { IndexModel } from "./schemas";
import { isFullIndexRow, isStaticCompositeRow } from "./leaderboard-score";

// The /leaderboard splits the catalog into the scoped ranked board and the not-yet-benchmarked
// shells. Score-less shells NEVER enter or sort into the ranked board (board-display contract):
// the ranked board is the measured, conformance-passing, headline-lane (HEADLINE_LANE) scope only.
// Anything measured but outside that scope (e.g. an answer-only ablation) is in NEITHER bucket —
// it lives on the model detail page as a diagnostic, not on the leaderboard.
export function splitLeaderboard(models: readonly IndexModel[]): {
  readonly ranked: readonly IndexModel[];
  readonly staticComposite: readonly IndexModel[];
  readonly catalog: readonly IndexModel[];
} {
  const ranked = models.filter(isFullIndexRow);
  const staticComposite = models.filter(isStaticCompositeRow);
  const catalog = models.filter(
    (model) => !isStaticCompositeRow(model) && (model.score_status === "missing" || model.composite === null),
  );
  return { ranked, staticComposite, catalog };
}

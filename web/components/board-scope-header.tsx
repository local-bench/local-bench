import type { LeaderboardScoreMode } from "@/lib/leaderboard-score";
import { INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

export const BOARD_SCOPE_TITLE = "Local Intelligence Index | index-v3.0";
export const BOARD_SCOPE_SUBTITLE =
  "Headline = 0.40 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.15 Coding + 0.05 Math. Ranks require all headline axes in this scope.";
export const STATIC_SCOPE_TITLE = "Static Index | static-suite-v2";
export const STATIC_SCOPE_SUBTITLE =
  "Secondary, provisional track while agentic verification is pending: Knowledge 25 + Instruction 25 + Tool calling 20 + Coding 20 + Math 10. It never competes with the six-axis Local Intelligence Index.";
export const SEASON_2_SCOPE_TITLE = "Local Intelligence Index | index-v4.0";
export const SEASON_2_SCOPE_SUBTITLE =
  "Headline = 0.20 Tool use + 0.24 Knowledge + 0.24 Instruction + 0.24 Coding + 0.08 Math. Tool use is bench-normalized across its declared facets; ranks require the complete season-2 profile.";

export function BoardScopeHeader({
  mode = "full",
  indexVersion,
}: {
  readonly mode?: LeaderboardScoreMode;
  readonly indexVersion?: string | undefined;
}) {
  const season2 = mode === "full" && indexVersion === INDEX_VERSION_V4;
  const title = mode === "static" ? STATIC_SCOPE_TITLE : season2 ? SEASON_2_SCOPE_TITLE : BOARD_SCOPE_TITLE;
  const subtitle = mode === "static" ? STATIC_SCOPE_SUBTITLE : season2 ? SEASON_2_SCOPE_SUBTITLE : BOARD_SCOPE_SUBTITLE;
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-muted">{title}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{subtitle}</p>
    </div>
  );
}

import type { LeaderboardScoreMode } from "@/lib/leaderboard-score";

export const BOARD_SCOPE_TITLE = "Local Intelligence Index | index-v3.0";
export const BOARD_SCOPE_SUBTITLE =
  "Headline = 0.40 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.15 Coding + 0.05 Math. Ranks require all headline axes in this scope.";
export const STATIC_SCOPE_TITLE = "Static Index | static-suite-v2";
export const STATIC_SCOPE_SUBTITLE =
  "Secondary, provisional track while agentic verification is pending: Knowledge 25 + Instruction 25 + Tool calling 20 + Coding 20 + Math 10. It never competes with the six-axis Local Intelligence Index.";

export function BoardScopeHeader({ mode = "full" }: { readonly mode?: LeaderboardScoreMode }) {
  const title = mode === "static" ? STATIC_SCOPE_TITLE : BOARD_SCOPE_TITLE;
  const subtitle = mode === "static" ? STATIC_SCOPE_SUBTITLE : BOARD_SCOPE_SUBTITLE;
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-muted">{title}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{subtitle}</p>
    </div>
  );
}

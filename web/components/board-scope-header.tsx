import type { LeaderboardScoreMode } from "@/lib/leaderboard-score";

export const BOARD_SCOPE_TITLE = "Local Intelligence Index | v2.1 modular";
export const BOARD_SCOPE_SUBTITLE =
  "Local open-weight models on one RTX 5090 (32 GB), reasoning on. Headline = 0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.10 Coding. Ranks require all headline axes in this scope.";
export const STATIC_SCOPE_TITLE = "No-agentic lane | static-suite-v1";
export const STATIC_SCOPE_SUBTITLE =
  "Fallback lane for platforms that cannot run the agentic sandbox. Rows here rank only against each other on the renormalized static composite (Knowledge 30 + Instruction 30 + Tool calling 20 + Coding 20) — never against, and never comparable with, the main Index.";

export function BoardScopeHeader({ mode = "full" }: { readonly mode?: LeaderboardScoreMode }) {
  const title = mode === "static" ? STATIC_SCOPE_TITLE : BOARD_SCOPE_TITLE;
  const subtitle = mode === "static" ? STATIC_SCOPE_SUBTITLE : BOARD_SCOPE_SUBTITLE;
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">{title}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{subtitle}</p>
    </div>
  );
}

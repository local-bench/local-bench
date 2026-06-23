// Scope frame for the ranked headline board. The lane / hardware / thinking-cap define what a
// rank MEANS, so they ride INSIDE the table frame (so the scope travels with screenshots),
// per the board-display contract. v1: every ranked row is the RTX 5090 project-anchor in the
// capped-thinking lane, so the scope is board-level and fixed. At v2 (community / other-
// hardware runs) this must derive from the data instead of staying hardcoded.
export const BOARD_SCOPE_TITLE = "Local Intelligence Index · capped-thinking lane";
export const BOARD_SCOPE_SUBTITLE =
  "Local open-weight models, RTX 5090 32GB, reasoning ON, 8192-token thinking cap. Ranks valid only within this lane.";

export function BoardScopeHeader() {
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">{BOARD_SCOPE_TITLE}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{BOARD_SCOPE_SUBTITLE}</p>
    </div>
  );
}

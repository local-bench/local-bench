// Scope frame for the ranked headline board. The hardware + Index definition define what a rank
// MEANS, so they ride INSIDE the table frame (so the scope travels with screenshots), per the
// board-display contract. v2.0: every ranked row is the RTX 5090 project-anchor on the agentic-led
// Index, so the scope is board-level and fixed. When community / other-hardware runs land this must
// derive from the data instead of staying hardcoded.
export const BOARD_SCOPE_TITLE = "Local Intelligence Index · v2.0 (agentic-led)";
export const BOARD_SCOPE_SUBTITLE =
  "Local open-weight models on one RTX 5090 (32 GB), reasoning on. Headline = 0.70 Agentic (AppWorld-C) + 0.15 Knowledge + 0.15 Instruction. Ranks valid within this scope.";

export function BoardScopeHeader() {
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">{BOARD_SCOPE_TITLE}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{BOARD_SCOPE_SUBTITLE}</p>
    </div>
  );
}

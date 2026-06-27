export const BOARD_SCOPE_TITLE = "Local Intelligence Index | v2.1 modular";
export const BOARD_SCOPE_SUBTITLE =
  "Local open-weight models on one RTX 5090 (32 GB), reasoning on. Headline = 0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.10 Coding. Ranks require all headline axes in this scope.";

export function BoardScopeHeader() {
  return (
    <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">{BOARD_SCOPE_TITLE}</p>
      <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">{BOARD_SCOPE_SUBTITLE}</p>
    </div>
  );
}

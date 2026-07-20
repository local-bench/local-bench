export function LeaderboardVariantToggle({
  showAllVariants,
  toggle,
}: {
  readonly showAllVariants: boolean;
  readonly toggle: () => void;
}) {
  return (
    <div className="border-b border-bench-line px-3 py-2">
      <button
        type="button"
        aria-pressed={showAllVariants}
        className={[
          "rounded border px-3 py-1.5 font-mono text-xs transition-colors",
          showAllVariants
            ? "border-bench-accent bg-bench-accent text-bench-bg"
            : "border-bench-line bg-bench-panel-2 text-bench-muted hover:border-bench-accent hover:text-bench-text",
        ].join(" ")}
        onClick={toggle}
      >
        {showAllVariants ? "Show best per family" : "Show all variants"}
      </button>
    </div>
  );
}

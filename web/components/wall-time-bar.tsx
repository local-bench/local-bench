import { formatDuration } from "@/lib/format";

// Shared measurement row for the two benchmarking-time panels (landing + model
// page): relative-width bar, printed duration, flame on the shortest run. One
// visual language in one place so the panels cannot drift apart again (owner
// call, 2026-07-25 — converge on the model-page style). Sort order remains each
// panel's own concern: rank on the landing board, elapsed time within a family.
export function WallTimeBar({
  maxWallTimeSeconds,
  shortest,
  wallTimeSeconds,
}: {
  readonly maxWallTimeSeconds: number;
  readonly shortest: boolean;
  readonly wallTimeSeconds: number | null;
}) {
  const hasTime = wallTimeSeconds !== null && wallTimeSeconds > 0;
  return (
    <div className="mt-1.5 grid grid-cols-[minmax(0,1fr)_66px] items-center gap-2.5">
      <div className="h-3.5 rounded bg-white/[0.05]">
        {hasTime ? (
          <div
            className="h-3.5 rounded-[3px] bg-gradient-to-r from-bench-accent-dim to-bench-accent"
            style={{ width: `${Math.min(100, (wallTimeSeconds / maxWallTimeSeconds) * 100)}%` }}
          />
        ) : null}
      </div>
      <div className="text-right font-mono text-xs tabular-nums text-bench-text">
        {hasTime ? formatDuration(wallTimeSeconds) : "—"}
        {hasTime && shortest ? (
          <span
            className="ml-1 cursor-default text-[11px]"
            role="img"
            aria-label="Shortest full-suite run this season"
            title="Shortest full-suite run this season"
          >
            🔥
          </span>
        ) : null}
      </div>
    </div>
  );
}

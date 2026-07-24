import { formatDuration } from "@/lib/format";

// Shared measurement row for the two time-to-complete panels (landing + model
// page): relative-width bar with the duration printed ON the bar (owner call,
// 2026-07-25) — inside the fill when it fits, just past the fill's end when the
// bar is short. Flame marks the shortest run. One visual language in one place
// so the panels cannot drift apart again. Sort order remains each panel's own
// concern.
const INSIDE_LABEL_MIN_PERCENT = 30;

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
  const percent = hasTime ? Math.min(100, (wallTimeSeconds / maxWallTimeSeconds) * 100) : 0;
  const labelInside = percent >= INSIDE_LABEL_MIN_PERCENT;
  return (
    <div className="relative mt-1.5 h-5 rounded bg-white/[0.05]">
      {hasTime ? (
        <div
          className="h-5 rounded-[3px] bg-gradient-to-r from-bench-accent-dim to-bench-accent"
          style={{ width: `${percent}%` }}
        />
      ) : null}
      <span
        className={`absolute top-0 flex h-5 items-center whitespace-nowrap font-mono text-[11px] tabular-nums ${
          hasTime
            ? labelInside
              ? "-translate-x-full pr-1.5 font-semibold text-bench-bg"
              : "pl-1.5 text-bench-text"
            : "pl-1.5 text-bench-muted"
        }`}
        style={{ left: `${percent}%` }}
      >
        {hasTime ? formatDuration(wallTimeSeconds) : "—"}
        {hasTime && shortest ? (
          <span
            className="ml-1 cursor-default"
            role="img"
            aria-label="Shortest full-suite run this season"
            title="Shortest full-suite run this season"
          >
            🔥
          </span>
        ) : null}
      </span>
    </div>
  );
}

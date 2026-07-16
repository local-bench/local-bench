import Link from "next/link";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { familyStyle } from "@/lib/family-color";
import { orgLogoForModelLabel } from "@/lib/family-logo";
import { formatCi, formatCompactNumber, formatDuration } from "@/lib/format";
import type { BestVariantPoint } from "@/lib/best-variant";

// Replication-time panel (oracle-amended spec, 2026-07-15): the landing card that answers
// "what does it cost to reproduce these leaderboard results on the reference rig". It is a
// cost chart, never a speed ranking — rows sort by leaderboard rank, the copy never says
// fastest/slowest, and the limitation sentence is visible text, not tooltip-only.
//
// Scope facts (item count, rig) are board-level and not carried on BestVariantPoint; keep in
// sync with the methodology page until the board manifest exposes them to the web layer.
const PANEL_SCOPE = "Season 2 · index v4.0 · 1,457 items · RTX 5090 reference rig";
const LIMITATION = "Elapsed time for this exact full-suite run; not a general model-speed measurement.";

// Render gates: the comparative chart renders only while timing coverage honestly represents
// the ranked board — at least 4 timed rows, at least 60% coverage, and a timed #1. Below any
// of those, a non-ranking fallback keeps the estimator path visible instead.
const MIN_TIMED_ROWS = 4;
const MIN_TIMED_COVERAGE = 0.6;
const MAX_LANDING_ROWS = 8;

function axisUpperBoundHours(maxHours: number): number {
  return Math.max(5, Math.ceil(maxHours / 5) * 5);
}

export function ReplicationTimePanel({ points }: { readonly points: readonly BestVariantPoint[] }) {
  // Rank identically to BestVariantTable (score descending) so the two can never disagree.
  const rows = [...points].sort((left, right) => right.score.point - left.score.point);
  const timed = rows.filter((row) => row.wallTimeSeconds !== null && row.wallTimeSeconds > 0);
  const coverageOk =
    timed.length >= MIN_TIMED_ROWS &&
    rows.length > 0 &&
    timed.length / rows.length >= MIN_TIMED_COVERAGE &&
    rows[0] !== undefined &&
    rows[0].wallTimeSeconds !== null &&
    rows[0].wallTimeSeconds > 0;

  return (
    <section
      data-testid="replication-time-panel"
      className="flex flex-col overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">
          Full-suite replication time
        </p>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-bench-muted-2">{PANEL_SCOPE}</p>
        <p className="mt-1 text-xs leading-5 text-bench-muted">
          End-to-end wall time for each ranked run. Output length affects totals —{" "}
          <span className="font-semibold text-bench-text">this is not an inference-speed ranking.</span>
        </p>
        <p className="mt-1 font-mono text-[11px] text-bench-accent">
          {timed.length} of {rows.length} ranked best variant{rows.length === 1 ? "" : "s"} have verified timing
        </p>
      </div>

      {coverageOk ? (
        <PanelBars rows={rows} timed={timed} />
      ) : (
        <div className="px-3 py-4 text-xs leading-5 text-bench-muted">
          {rows.length === 0
            ? "No comparable full-suite timings have been published for this season yet. Timing resets when the suite changes."
            : "There are not yet enough comparable timings to represent current leaderboard runs honestly."}
        </div>
      )}

      <div className="mt-auto border-t border-bench-line px-3 py-2.5">
        <a
          href="#run-it-yourself"
          className="font-mono text-xs text-bench-accent underline decoration-dotted underline-offset-4 hover:text-bench-text"
        >
          Estimate a full-suite run →
        </a>
      </div>
    </section>
  );
}

function PanelBars({
  rows,
  timed,
}: {
  readonly rows: readonly BestVariantPoint[];
  readonly timed: readonly BestVariantPoint[];
}) {
  const display = rows.slice(0, MAX_LANDING_ROWS);
  const untimedShown = display.filter((row) => row.wallTimeSeconds === null || row.wallTimeSeconds <= 0);
  // Owner call (2026-07-16): mark the shortest run with a flame. Copy stays run-oriented
  // ("shortest full-suite run"), never "fastest model" — see the panel's misread guard.
  const shortestRunId = timed.reduce((best, row) =>
    (row.wallTimeSeconds ?? Infinity) < (best.wallTimeSeconds ?? Infinity) ? row : best,
  ).runId;
  const maxHours = Math.max(...timed.map((row) => (row.wallTimeSeconds ?? 0) / 3600));
  const axisMax = axisUpperBoundHours(maxHours);
  const tickStep = axisMax >= 20 ? 10 : 5;
  const ticks: number[] = [];
  for (let tick = tickStep; tick < axisMax; tick += tickStep) {
    ticks.push(tick);
  }

  return (
    <div className="px-3 py-2">
      {display.map((row, index) => {
        const wall = row.wallTimeSeconds;
        const hasTime = wall !== null && wall > 0;
        return (
          <div
            key={row.runId}
            tabIndex={0}
            className="group relative border-t border-bench-line/40 py-2 outline-none transition-colors first:border-t-0 hover:bg-white/[0.035] focus-visible:bg-white/[0.035]"
          >
            <div className="pointer-events-none absolute bottom-[calc(100%-4px)] left-0 z-10 w-[280px] rounded border border-bench-line-strong bg-bench-bg px-2 py-1.5 font-mono text-[11px] leading-4 text-bench-muted opacity-0 shadow-2xl shadow-black/30 transition-opacity duration-100 group-hover:opacity-100 group-focus-visible:opacity-100">
              <span className="font-semibold text-bench-text">{row.modelLabel}</span>
              {row.tokS !== null ? <> · {formatCompactNumber(row.tokS)} tok/s effective</> : null}
              {" · CI "}
              {formatCi(row.score)}
              <br />
              <span className="text-bench-warn-soft">{LIMITATION}</span>
            </div>

            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              {orgLogoForModelLabel(row.modelLabel) !== null ? (
                <FamilyLogoMark modelLabel={row.modelLabel} size={15} />
              ) : (
                <span
                  aria-hidden
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: familyStyle(row.family).color }}
                />
              )}
              <Link
                href={`/model/${row.modelSlug}`}
                className="text-[13px] font-semibold text-bench-text hover:text-bench-accent"
              >
                {row.modelLabel}
              </Link>
              {row.quantLabel ? <span className="font-mono text-[10px] text-bench-muted-2">{row.quantLabel}</span> : null}
              <span className="ml-auto flex items-baseline gap-1.5">
                <span
                  className={`rounded-full border px-1.5 py-px font-mono text-[10px] ${
                    index === 0 ? "border-bench-accent/50 text-bench-accent" : "border-bench-line-strong text-bench-text"
                  }`}
                >
                  #{index + 1}
                </span>
                <span className="font-mono text-[11px] tabular-nums text-bench-muted">{row.score.point.toFixed(2)}</span>
              </span>
            </div>

            <div className="mt-1.5 grid grid-cols-[minmax(0,1fr)_66px] items-center gap-2.5">
              <div className="relative h-3.5 rounded bg-white/[0.05]">
                {ticks.map((tick) => (
                  <span
                    key={tick}
                    aria-hidden
                    className="absolute -bottom-0.5 -top-0.5 w-px bg-bench-grid"
                    style={{ left: `${(tick / axisMax) * 100}%` }}
                  />
                ))}
                {hasTime ? (
                  <div
                    className="relative z-[1] h-3.5 rounded-[3px] bg-gradient-to-r from-bench-accent-dim to-bench-accent"
                    style={{ width: `${Math.min(100, ((wall / 3600) / axisMax) * 100)}%` }}
                  />
                ) : null}
              </div>
              <div className="text-right font-mono text-xs tabular-nums text-bench-text">
                {hasTime ? formatDuration(wall) : "—"}
                {hasTime && row.runId === shortestRunId ? (
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
          </div>
        );
      })}

      <div className="mt-1 grid grid-cols-[minmax(0,1fr)_66px] gap-2.5">
        <div className="relative h-3 font-mono text-[9px] text-bench-muted-2">
          <span className="absolute left-0">0</span>
          {ticks.map((tick) => (
            <span key={tick} className="absolute -translate-x-1/2" style={{ left: `${(tick / axisMax) * 100}%` }}>
              {tick} h
            </span>
          ))}
          <span className="absolute right-0">{axisMax} h</span>
        </div>
        <div />
      </div>

      {untimedShown.length > 0 ? (
        <p className="mt-2 rounded border border-dashed border-bench-line-strong px-2 py-1.5 text-[11px] leading-4 text-bench-muted-2">
          Timing unavailable in the board record for {untimedShown.length} ranked variant
          {untimedShown.length === 1 ? "" : "s"}. Season 2 community submissions do not ingest timing fields.
        </p>
      ) : null}

      {rows.length > MAX_LANDING_ROWS ? (
        <p className="mt-2 text-[11px] leading-4 text-bench-muted-2">
          Showing {MAX_LANDING_ROWS} of {rows.length} ranked models —{" "}
          <Link href="/leaderboard" className="text-bench-accent underline hover:text-bench-text">
            view all timings in the leaderboard
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}

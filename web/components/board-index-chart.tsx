import Link from "next/link";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import {
  BAR_WIDTH,
  PLOT,
  SLOT_WIDTH,
  SVG_HEIGHT,
  TICKS,
  scaleY,
  toChartRows,
} from "@/lib/board-index-chart-layout";
import { familyStyle } from "@/lib/family-color";
import { formatScore } from "@/lib/format";
import type { IndexModel } from "@/lib/schemas";
import { hasCompleteSeason2Coverage } from "@/lib/scoring-seasons";

export function BoardIndexChart({ models }: { readonly models: readonly IndexModel[] }) {
  const rows = toChartRows(models);
  const season2 = models.some(hasCompleteSeason2Coverage);
  if (rows.length === 0) {
    return null;
  }

  const width = PLOT.left + PLOT.right + rows.length * SLOT_WIDTH;
  const first = rows[0];
  const last = rows.at(-1);
  const ariaLabel =
    first === undefined || last === undefined
      ? "Bar chart of ranked variants by Local Intelligence Index"
      : `Bar chart of ${rows.length} ranked variants by Local Intelligence Index, highest ${formatScore(
          first.score.point,
        )} lowest ${formatScore(last.score.point)}`;

  return (
    <section
      data-testid="leaderboard-index-chart"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <div className="border-b border-bench-line bg-white/[0.02] px-3 py-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Full board</p>
        <h2 className="mt-1 text-2xl font-semibold text-bench-text">Local Intelligence Index — ranked</h2>
        {season2 ? (
          <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">
            Each bar is one ranked variant, colored by model family. Hover or focus a bar for its five-axis season-2
            breakdown and the score&apos;s uncertainty range.
          </p>
        ) : (
          <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">
            Each bar is one ranked variant, colored by model family. Hover or focus a bar for its six-axis breakdown
            and the score&apos;s uncertainty range.
          </p>
        )}
        <p className="sr-only">The ranked table below lists the same data in sortable text.</p>
      </div>
      <p className="border-b border-bench-line px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-bench-accent md:hidden">
        Swipe horizontally to see all ranked bars →
      </p>
      <div className="overflow-x-auto px-3 pb-4 pt-4">
        <div className="relative" style={{ width }}>
          <svg
            role="group"
            aria-label={ariaLabel}
            viewBox={`0 0 ${width} ${SVG_HEIGHT}`}
            className="block h-[300px] max-w-none"
            style={{ width }}
          >
            <rect width={width} height={SVG_HEIGHT} className="fill-bench-panel" />
            {TICKS.map((tick) => {
              const y = scaleY(tick);
              return (
                <g key={tick}>
                  <line x1={PLOT.left} x2={width - PLOT.right} y1={y} y2={y} className="stroke-bench-line" />
                  <text x={PLOT.left - 10} y={y + 4} className="fill-bench-muted" fontSize="11" textAnchor="end">
                    {tick}
                  </text>
                </g>
              );
            })}
            <line
              x1={PLOT.left}
              x2={width - PLOT.right}
              y1={scaleY(0)}
              y2={scaleY(0)}
              className="stroke-bench-line-strong"
            />
            <line
              x1={PLOT.left}
              x2={PLOT.left}
              y1={PLOT.top}
              y2={scaleY(0)}
              className="stroke-bench-line-strong"
            />
            {rows.map((row) => (
              <g
                key={row.model.slug}
                aria-hidden="true"
                data-bar-center={row.barCenter}
                data-bar-top={row.barTop}
                data-chart-bar={row.model.slug}
              >
                <title>{row.tooltipLines.join(" | ")}</title>
                <path
                  d={barPath(row.barLeft, row.barTop, BAR_WIDTH, scaleY(0))}
                  data-bar-fill={familyStyle(row.model.family).color}
                  fill={familyStyle(row.model.family).color}
                  fillOpacity="0.88"
                />
                <text
                  x={row.barCenter}
                  y={valueLabelY(row.barTop, scaleY(0))}
                  className={scaleY(0) - row.barTop < 24 ? "fill-bench-text" : "fill-bench-bg"}
                  fontSize="12"
                  fontWeight="600"
                  fontFamily="var(--font-mono)"
                  textAnchor="middle"
                >
                  {formatScore(row.score.point)}
                </text>
              </g>
            ))}
          </svg>
          <div
            className="grid"
            style={{
              gridTemplateColumns: `repeat(${rows.length}, ${SLOT_WIDTH}px)`,
              marginLeft: PLOT.left,
              marginRight: PLOT.right,
            }}
          >
            {rows.map((row, index) => (
              <div
                key={row.model.slug}
                data-chart-label={row.model.slug}
                data-label-center={row.labelCenter}
                className="group relative h-[96px] min-w-0"
              >
                <span
                  data-tooltip-hit-target={row.model.slug}
                  aria-hidden="true"
                  className="absolute bottom-full left-1/2 h-[252px] w-20 -translate-x-1/2"
                />
                <span
                  role="tooltip"
                  className={`pointer-events-none absolute bottom-[calc(100%+8px)] z-10 w-[260px] rounded border border-bench-line-strong bg-bench-bg px-2 py-1.5 text-left font-mono text-[11px] leading-4 text-bench-muted opacity-0 shadow-2xl shadow-black/30 transition-opacity duration-100 group-hover:opacity-100 group-focus-within:opacity-100 ${tooltipPositionClass(index, rows.length)}`}
                >
                  {row.tooltipLines.map((line, index) => (
                    <span key={line} className={index === 0 ? "block text-bench-text" : "block"}>
                      {line}
                    </span>
                  ))}
                </span>
                {/* Angled label, top-right corner anchored under the bar center (the AA layout). */}
                <div className="absolute right-1/2 top-1.5 origin-top-right -rotate-[36deg]">
                  <Link
                    href={`/model/${row.model.slug}`}
                    className="flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold leading-4 text-bench-text hover:text-bench-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bench-accent"
                  >
                    <FamilyLogoMark modelLabel={row.model.model_label} size={14} />
                    {row.model.model_label}
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// Score sits centered inside the bar (the AA layout); a bar too short to hold the text
// gets the label just above its top instead.
function valueLabelY(barTop: number, baseline: number): number {
  return baseline - barTop < 24 ? Math.max(14, barTop - 8) : (barTop + baseline) / 2 + 4;
}

// Rounded-top bar outline (top corners only — the base sits flush on the axis line).
function barPath(left: number, top: number, width: number, baseline: number): string {
  const radius = Math.min(5, Math.max(0, baseline - top), width / 2);
  const right = left + width;
  return [
    `M ${left} ${baseline}`,
    `L ${left} ${top + radius}`,
    `Q ${left} ${top} ${left + radius} ${top}`,
    `L ${right - radius} ${top}`,
    `Q ${right} ${top} ${right} ${top + radius}`,
    `L ${right} ${baseline}`,
    "Z",
  ].join(" ");
}

function tooltipPositionClass(index: number, total: number): string {
  if (index === 0) {
    return "left-0";
  }
  if (index === total - 1) {
    return "right-0";
  }
  return "left-1/2 -translate-x-1/2";
}

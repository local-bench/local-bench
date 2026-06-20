import { formatCoreTextAxisProfile } from "@/components/local-intelligence-index";
import { DEFAULT_CONTEXT_TOKENS, formatContextLength } from "@/lib/rig-match";
import { formatGb, formatScore } from "@/lib/format";
import { familyStyle } from "@/lib/family-color";
import type { AnchorReference } from "@/lib/data";
import type { BestVariantPoint } from "@/lib/best-variant";

const WIDTH = 920;
const HEIGHT = 460;
const PLOT = { left: 64, right: 188, top: 30, bottom: 64 } as const;
const Y_TICKS = [100, 75, 50, 25, 0] as const;
// Reference tiers reach down to small/laptop cards (2-6 GB) — that low-RAM region is exactly
// where local models earn their keep, so it should be marked, not hidden below an 8 GB floor.
const X_TIERS = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512] as const;

type Domain = { readonly min: number; readonly max: number };

export function BestVariantVramScatter({
  anchorRuns,
  points,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly points: readonly BestVariantPoint[];
}) {
  const domain = getLogDomain(points);
  const anchors = layoutAnchors(anchorRuns);
  const frontier = [...points]
    .filter((point) => point.isFrontier)
    .sort((left, right) => left.effectiveVramGb - right.effectiveVramGb);
  const frontierPath = frontier
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${scaleX(point.effectiveVramGb, domain).toFixed(1)} ${scaleY(point.score.point).toFixed(1)}`,
    )
    .join(" ");
  const legend = [
    ...new Map(
      points.map((point) => {
        const style = familyStyle(point.family);
        return [style.label, style.color] as const;
      }),
    ),
  ];
  // Declutter: label frontier points greedily by score, skipping any that would collide with an
  // already-placed label. Colour + legend + hover identify the rest, so the plot stays readable as
  // the model count grows.
  const placedBoxes: { x1: number; y1: number; x2: number; y2: number }[] = [];
  const labelledIds = new Set<string>();
  for (const candidate of [...points].filter((entry) => entry.isFrontier).sort((a, b) => b.score.point - a.score.point)) {
    const cx = scaleX(candidate.effectiveVramGb, domain);
    const cy = scaleY(candidate.score.point);
    const width = candidate.modelLabel.length * 6.6 + 6;
    const box = { x1: cx + 9, y1: cy - 25, x2: cx + 9 + width, y2: cy - 3 };
    const overlaps = placedBoxes.some(
      (placed) => box.x1 < placed.x2 && box.x2 > placed.x1 && box.y1 < placed.y2 && box.y2 > placed.y1,
    );
    if (!overlaps && box.x2 < WIDTH - 6) {
      placedBoxes.push(box);
      labelledIds.add(candidate.runId);
    }
  }

  return (
    <section
      data-testid="best-variant-scatter"
      className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20"
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase text-bench-accent">Best variant per model</p>
          <h2 className="mt-1 text-lg font-semibold text-bench-text">Quality vs the VRAM to run it</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-bench-muted">
            Each point is a model at its best-scoring quant. Up = smarter; left = fits a smaller card. The dotted line
            is the point-estimate efficiency frontier — no measured model is both higher-scoring and smaller on current
            point estimates. Hover any point for details.
          </p>
        </div>
        <div className="font-mono text-xs text-bench-muted">{points.length} models</div>
      </div>
      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label={describe(points)}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[340px] sm:min-w-[820px]"
        >
          <rect width={WIDTH} height={HEIGHT} className="fill-bench-panel" />
          {Y_TICKS.map((tick) => {
            const y = scaleY(tick);
            return (
              <g key={tick}>
                <line x1={PLOT.left} x2={WIDTH - PLOT.right} y1={y} y2={y} className="stroke-bench-line" />
                <text x={PLOT.left - 12} y={y + 4} className="fill-bench-muted" fontSize="12" textAnchor="end">
                  {tick}
                </text>
              </g>
            );
          })}
          {X_TIERS.map((tier) => {
            if (tier < domain.min || tier > domain.max) {
              return null;
            }
            const x = scaleX(tier, domain);
            return (
              <g key={tier}>
                <line
                  x1={x}
                  x2={x}
                  y1={PLOT.top}
                  y2={HEIGHT - PLOT.bottom}
                  className="stroke-bench-line"
                  strokeDasharray="3 9"
                />
                <text x={x + 4} y={HEIGHT - PLOT.bottom - 6} className="fill-bench-muted-2" fontSize="11">
                  {tier}GB
                </text>
              </g>
            );
          })}
          <line
            x1={PLOT.left}
            x2={WIDTH - PLOT.right}
            y1={HEIGHT - PLOT.bottom}
            y2={HEIGHT - PLOT.bottom}
            className="stroke-bench-line-strong"
          />
          <line x1={PLOT.left} x2={PLOT.left} y1={PLOT.top} y2={HEIGHT - PLOT.bottom} className="stroke-bench-line-strong" />
          {anchors.map(({ anchor, lineY, labelY }) => (
            <g key={anchor.run_id}>
              <line
                x1={PLOT.left}
                x2={WIDTH - PLOT.right}
                y1={lineY}
                y2={lineY}
                className="stroke-bench-anchor"
                strokeDasharray="7 6"
                strokeWidth="1.5"
              />
              <text x={WIDTH - PLOT.right + 12} y={labelY} className="fill-bench-anchor-soft" fontSize="12">
                {anchor.model_label} {formatScore(anchor.composite.point)}
              </text>
            </g>
          ))}
          {frontier.length > 1 ? (
            <path d={frontierPath} className="fill-none stroke-bench-accent-dim" strokeWidth="1.5" strokeDasharray="2 5" />
          ) : null}
          {points.map((point) => {
            const cx = scaleX(point.effectiveVramGb, domain);
            const cy = scaleY(point.score.point);
            const lo = scaleY(point.score.lo);
            const hi = scaleY(point.score.hi);
            const color = familyStyle(point.family).color;
            return (
              <g key={point.runId} opacity={point.isFrontier ? 1 : 0.5}>
                <title>
                  {`${point.modelLabel}${point.quantLabel ? ` (${point.quantLabel})` : ""}: ${formatScore(point.score.point)} — ${formatCoreTextAxisProfile(point.axes)} — ~${formatGb(point.effectiveVramGb)} to run`}
                </title>
                <line x1={cx} x2={cx} y1={hi} y2={lo} stroke={color} strokeWidth="1.5" />
                <circle cx={cx} cy={cy} r={point.isFrontier ? 6 : 4} fill={color} className="stroke-bench-bg" strokeWidth="2" />
                {labelledIds.has(point.runId) ? (
                  <text x={cx + 9} y={cy - 9} className="fill-bench-text" fontSize="12">
                    {point.modelLabel}
                  </text>
                ) : null}
              </g>
            );
          })}
          {points.length === 0 ? (
            <text
              x={(WIDTH - PLOT.right + PLOT.left) / 2}
              y={HEIGHT / 2}
              className="fill-bench-muted"
              fontSize="14"
              textAnchor="middle"
            >
              No measured local models yet — points appear here as runs land.
            </text>
          ) : null}
          <text
            x={(WIDTH - PLOT.right + PLOT.left) / 2}
            y={HEIGHT - 16}
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="middle"
          >
            effective VRAM to run · {formatContextLength(DEFAULT_CONTEXT_TOKENS)} context (GB, log scale)
          </text>
          <text
            x="18"
            y={(PLOT.top + HEIGHT - PLOT.bottom) / 2}
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="middle"
            transform={`rotate(-90 18 ${(PLOT.top + HEIGHT - PLOT.bottom) / 2})`}
          >
            Local Intelligence Index
          </text>
        </svg>
      </div>
      {legend.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-bench-muted">
          {legend.map(([label, color]) => (
            <span key={label} className="inline-flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
              {label}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-bench-muted-2">
        <span>labelled = efficiency frontier</span>
        <span>faded = beaten at its size</span>
        <span>vertical bars = 95% CI</span>
        <span>dashed gold = frontier (API) ceilings</span>
      </div>
    </section>
  );
}

function scaleY(value: number): number {
  const height = HEIGHT - PLOT.top - PLOT.bottom;
  return PLOT.top + (1 - value / 100) * height;
}

function getLogDomain(points: readonly BestVariantPoint[]): Domain {
  const values = points.map((point) => point.effectiveVramGb).filter((value) => value > 0);
  if (values.length === 0) {
    return { min: 8, max: 96 };
  }
  // Snap the max out to at least the next GPU tier (never below 24 GB) so the rig-tier markers stay
  // on the chart even when the first measured ladder is all small models.
  const padded = Math.max(...values) * 1.3;
  const snapped = X_TIERS.find((tier) => tier >= padded) ?? padded;
  return { min: Math.max(0.5, Math.min(...values) / 1.3), max: Math.max(24, snapped) };
}

function scaleX(value: number, domain: Domain): number {
  const width = WIDTH - PLOT.left - PLOT.right;
  const lo = Math.log2(domain.min);
  const hi = Math.log2(domain.max);
  const span = hi - lo || 1;
  const clamped = Math.max(value, domain.min);
  return PLOT.left + ((Math.log2(clamped) - lo) / span) * width;
}

function layoutAnchors(anchorRuns: readonly AnchorReference[]) {
  return [...anchorRuns]
    .sort((left, right) => right.composite.point - left.composite.point)
    .map((anchor, index) => {
      const lineY = scaleY(anchor.composite.point);
      return { anchor, lineY, labelY: Math.min(HEIGHT - PLOT.bottom - 10, lineY + index * 16 + 4) };
    });
}

function describe(points: readonly BestVariantPoint[]): string {
  if (points.length === 0) {
    return "Scatter of local model quality versus VRAM; no measured models yet.";
  }
  const best = points.reduce((top, point) => (point.score.point > top.score.point ? point : top));
  return `Scatter of ${points.length} local models: Local Intelligence Index versus effective VRAM to run. Best: ${best.modelLabel} at ${formatScore(best.score.point)}.`;
}

import { formatModularAxisProfile } from "@/components/local-intelligence-index";
import { formatGb, formatScore } from "@/lib/format";
import { familyStyle } from "@/lib/family-color";
import {
  getVramLogDomain,
  scaleVramLogX,
  VRAM_LOG_LABEL_TICKS,
  VRAM_LOG_TICKS,
} from "@/lib/vram-log-scale";
import type { AnchorReference } from "@/lib/data";
import type { BestVariantPoint } from "@/lib/best-variant";

const WIDTH = 920;
const HEIGHT = 460;
const PLOT = { left: 64, right: 188, top: 30, bottom: 64 } as const;
const VRAM_SCALE_LAYOUT = { left: PLOT.left, right: PLOT.right, width: WIDTH } as const;
const Y_TICKS = [100, 75, 50, 25, 0] as const;

// Candidate label positions around a point (dx/dy from the dot + text anchor), tried in order.
// Every point is labelled on this overview chart, so we try several slots and fall back to the
// first rather than dropping a label.
type LabelSlot = { readonly dx: number; readonly dy: number; readonly anchor: "start" | "end" };
const FALLBACK_SLOT: LabelSlot = { dx: 9, dy: -9, anchor: "start" };
const LABEL_SLOTS: readonly LabelSlot[] = [
  FALLBACK_SLOT,
  { dx: 9, dy: 18, anchor: "start" },
  { dx: -9, dy: -9, anchor: "end" },
  { dx: -9, dy: 18, anchor: "end" },
  { dx: 9, dy: 5, anchor: "start" },
  { dx: -9, dy: 5, anchor: "end" },
];

export function BestVariantVramScatter({
  anchorRuns,
  points,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly points: readonly BestVariantPoint[];
}) {
  const domain = getVramLogDomain(points.map((point) => point.effectiveVramGb));
  const anchors = layoutAnchors(anchorRuns);
  const frontier = [...points]
    .filter((point) => point.isFrontier)
    .sort((left, right) => left.effectiveVramGb - right.effectiveVramGb);
  const frontierPath = frontier
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${scaleVramLogX(point.effectiveVramGb, domain, VRAM_SCALE_LAYOUT).toFixed(1)} ${scaleY(point.score.point).toFixed(1)}`,
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
  // Label EVERY point so each dot is identifiable — a single labelled dot on a sparse board leaves
  // the rest anonymous. Place greedily by score so the leaders claim the clearest slots; try the
  // slots around each dot and fall back to the first so no dot is ever left unlabelled.
  const placedBoxes: { x1: number; y1: number; x2: number; y2: number }[] = [];
  const labelPlacements = new Map<string, LabelSlot>();
  for (const candidate of [...points].sort((a, b) => b.score.point - a.score.point)) {
    const cx = scaleVramLogX(candidate.effectiveVramGb, domain, VRAM_SCALE_LAYOUT);
    const cy = scaleY(candidate.score.point);
    const width = candidate.modelLabel.length * 6.6 + 6;
    const boxFor = (slot: LabelSlot) => {
      const x1 = slot.anchor === "end" ? cx + slot.dx - width : cx + slot.dx;
      const top = cy + slot.dy - 13;
      return { x1, y1: top, x2: x1 + width, y2: top + 18 };
    };
    const slot =
      LABEL_SLOTS.find((candidateSlot) => {
        const box = boxFor(candidateSlot);
        const overlaps = placedBoxes.some(
          (placed) => box.x1 < placed.x2 && box.x2 > placed.x1 && box.y1 < placed.y2 && box.y2 > placed.y1,
        );
        return !overlaps && box.x1 > 4 && box.x2 < WIDTH - 6;
      }) ?? FALLBACK_SLOT;
    placedBoxes.push(boxFor(slot));
    labelPlacements.set(candidate.runId, slot);
  }

  return (
    <section
      data-testid="best-variant-scatter"
      className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20"
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Best variant per model</p>
          <h2 className="mt-1 text-2xl font-semibold text-bench-text">Quality vs the VRAM to run it</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-bench-muted">
            Each point is a model at its best-scoring quant. Up = smarter; left = fits a smaller card.
            {/* The frontier line renders only at >=3 frontier points, so only describe it then. */}
            {frontier.length >= 3
              ? " The dotted line is the point-estimate efficiency frontier — no measured model is both higher-scoring and smaller on current point estimates."
              : ""}{" "}
            Hover any point for details.
          </p>
          {points.length < 4 ? (
            <p className="mt-1.5 font-mono text-[11px] text-bench-muted-2">
              Only {points.length} model{points.length === 1 ? "" : "s"} ranked so far — the size-vs-score frontier
              line appears once enough variants land.
            </p>
          ) : null}
        </div>
        <div className="font-mono text-xs text-bench-muted">{points.length} model{points.length === 1 ? "" : "s"}</div>
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
          {VRAM_LOG_TICKS.map((tier) => {
            if (tier < domain.min || tier > domain.max) {
              return null;
            }
            const x = scaleVramLogX(tier, domain, VRAM_SCALE_LAYOUT);
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
                {(VRAM_LOG_LABEL_TICKS as readonly number[]).includes(tier) ? (
                  <text x={x + 4} y={HEIGHT - PLOT.bottom - 6} className="fill-bench-muted-2" fontSize="11">
                    {tier}GB
                  </text>
                ) : null}
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
          {frontier.length >= 3 ? (
            <path d={frontierPath} className="fill-none stroke-bench-accent-dim" strokeWidth="1.5" strokeDasharray="2 5" />
          ) : null}
          {points.map((point) => {
            const cx = scaleVramLogX(point.effectiveVramGb, domain, VRAM_SCALE_LAYOUT);
            const cy = scaleY(point.score.point);
            const color = familyStyle(point.family).color;
            const slot = labelPlacements.get(point.runId);
            const tipLine1 = `${point.modelLabel}${point.quantLabel ? ` (${point.quantLabel})` : ""} — ${formatScore(point.score.point)}`;
            const tipLine2 = `${formatModularAxisProfile(point.axes)} · ~${formatGb(point.effectiveVramGb)} to run`;
            const tipWidth = Math.max(tipLine1.length, tipLine2.length) * 6.6 + 20;
            // Clamp the tooltip inside the plot; flip below the dot when it would clip the top.
            const tipX = Math.min(Math.max(cx - tipWidth / 2, 6), WIDTH - tipWidth - 6);
            const tipAbove = cy - 52 > 4;
            const tipY = tipAbove ? cy - 52 : cy + 14;
            return (
              // CSS-only hover: this is a server component, so the tooltip is an SVG group toggled
              // by group-hover — no client JS. The transparent r=14 circle is the hit target (the
              // visible 6px dot was too small to hover reliably).
              <g key={point.runId} className="group">
                <title>
                  {`${point.modelLabel}${point.quantLabel ? ` (${point.quantLabel})` : ""}: ${formatScore(point.score.point)} — ${formatModularAxisProfile(point.axes)} — ~${formatGb(point.effectiveVramGb)} to run`}
                </title>
                <circle cx={cx} cy={cy} r="14" fill="transparent" />
                <circle cx={cx} cy={cy} r="6" fill={color} className="stroke-bench-bg" strokeWidth="2" />
                {slot ? (
                  <text
                    x={cx + slot.dx}
                    y={cy + slot.dy}
                    textAnchor={slot.anchor}
                    className="fill-bench-text"
                    fontSize="12"
                  >
                    {point.modelLabel}
                  </text>
                ) : null}
                <g className="pointer-events-none opacity-0 transition-opacity duration-100 group-hover:opacity-100">
                  <rect
                    x={tipX}
                    y={tipY}
                    width={tipWidth}
                    height={38}
                    rx={4}
                    className="fill-bench-bg stroke-bench-line-strong"
                  />
                  <text x={tipX + 10} y={tipY + 16} className="fill-bench-text" fontSize="11" fontFamily="var(--font-mono)">
                    {tipLine1}
                  </text>
                  <text x={tipX + 10} y={tipY + 30} className="fill-bench-muted" fontSize="11" fontFamily="var(--font-mono)">
                    {tipLine2}
                  </text>
                </g>
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
              No ranked five-axis local rows yet; partial diagnostics stay off this frontier.
            </text>
          ) : null}
          <text
            x={(WIDTH - PLOT.right + PLOT.left) / 2}
            y={HEIGHT - 16}
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="middle"
          >
            effective VRAM to run (GB, log scale)
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
        <span>vertical guides = common VRAM tiers; horizontal guides = API model ceilings</span>
      </div>
    </section>
  );
}

function scaleY(value: number): number {
  const height = HEIGHT - PLOT.top - PLOT.bottom;
  return PLOT.top + (1 - value / 100) * height;
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
    return "Scatter of local model quality versus VRAM; no ranked five-axis local rows yet.";
  }
  const best = points.reduce((top, point) => (point.score.point > top.score.point ? point : top));
  return `Scatter of ${points.length} local models: Local Intelligence Index versus effective VRAM to run. Best: ${best.modelLabel} at ${formatScore(best.score.point)}.`;
}

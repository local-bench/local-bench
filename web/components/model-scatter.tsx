import { formatCi, formatGb, formatScore } from "@/lib/format";
import type { AnchorReference, ModelData, ModelRun } from "@/lib/data";

const WIDTH = 900;
const HEIGHT = 420;
const PLOT = {
  left: 62,
  right: 178,
  top: 28,
  bottom: 56,
} as const;
const Y_TICKS = [100, 75, 50, 25, 0] as const;

type ScatterPoint = {
  readonly run: ModelRun;
  readonly x: number;
};

export function ModelScatter({
  model,
  anchorRuns,
}: {
  readonly model: ModelData;
  readonly anchorRuns: readonly AnchorReference[];
}) {
  const points = model.runs.map(toScatterPoint).filter(isScatterPoint);
  const xDomain = getXDomain(points);
  const omitted = model.runs.length - points.length;
  const anchors = layoutAnchors(anchorRuns);

  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-bench-text">VRAM footprint vs composite</h2>
          <p className="text-sm text-bench-muted">Where your run lands vs other quants and the frontier anchors.</p>
        </div>
        <div className="font-mono text-xs text-bench-muted">{omitted} run(s) omitted from x-axis: no footprint</div>
      </div>
      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label={`${model.model_label} composite scatter with anchor reference lines`}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="min-w-[760px]"
        >
          <rect width={WIDTH} height={HEIGHT} className="fill-bench-panel" />
          {Y_TICKS.map((tick) => {
            const y = scaleY(tick);
            return (
              <g key={tick}>
                <line
                  x1={PLOT.left}
                  x2={WIDTH - PLOT.right}
                  y1={y}
                  y2={y}
                  className="stroke-bench-line"
                  strokeWidth="1"
                />
                <text x={PLOT.left - 12} y={y + 4} className="fill-bench-muted" fontSize="12" textAnchor="end">
                  {tick}
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
          <line
            x1={PLOT.left}
            x2={PLOT.left}
            y1={PLOT.top}
            y2={HEIGHT - PLOT.bottom}
            className="stroke-bench-line-strong"
          />
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
          {points.map((point) => {
            const cx = scaleX(point.x, xDomain);
            const cy = scaleY(point.run.composite.point);
            const lo = scaleY(point.run.composite.lo);
            const hi = scaleY(point.run.composite.hi);
            return (
              <g key={point.run.run_id}>
                <line x1={cx} x2={cx} y1={hi} y2={lo} className="stroke-bench-accent" strokeWidth="2" />
                <line
                  x1={cx - 6}
                  x2={cx + 6}
                  y1={hi}
                  y2={hi}
                  className="stroke-bench-accent"
                  strokeWidth="2"
                />
                <line
                  x1={cx - 6}
                  x2={cx + 6}
                  y1={lo}
                  y2={lo}
                  className="stroke-bench-accent"
                  strokeWidth="2"
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r="6"
                  className="fill-bench-accent stroke-bench-bg"
                  strokeWidth="2"
                />
                <text x={cx + 10} y={cy - 10} className="fill-bench-text" fontSize="12">
                  {point.run.quant_label ?? point.run.run_id.split("__")[1]}
                </text>
              </g>
            );
          })}
          {points.length === 0 ? (
            <text
              x={(WIDTH - PLOT.right + PLOT.left) / 2}
              y={210}
              className="fill-bench-muted"
              fontSize="14"
              textAnchor="middle"
            >
              No community runs include VRAM footprint yet.
            </text>
          ) : null}
          <text
            x={(WIDTH - PLOT.right + PLOT.left) / 2}
            y={HEIGHT - 18}
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="middle"
          >
            model memory footprint (GB)
          </text>
          <text
            x="18"
            y="210"
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="middle"
            transform="rotate(-90 18 210)"
          >
            composite
          </text>
          <text x={PLOT.left} y={HEIGHT - PLOT.bottom + 26} className="fill-bench-muted" fontSize="12">
            {formatGb(xDomain.min)}
          </text>
          <text
            x={WIDTH - PLOT.right}
            y={HEIGHT - PLOT.bottom + 26}
            className="fill-bench-muted"
            fontSize="12"
            textAnchor="end"
          >
            {formatGb(xDomain.max)}
          </text>
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-bench-muted">
        <span>Community points include vertical 95% CI whiskers.</span>
        <span>Anchor lines are dashed frontier references.</span>
      </div>
    </section>
  );
}

function toScatterPoint(run: ModelRun): ScatterPoint | null {
  return run.vram_footprint_gb === null ? null : { run, x: run.vram_footprint_gb };
}

function isScatterPoint(point: ScatterPoint | null): point is ScatterPoint {
  return point !== null;
}

function getXDomain(points: readonly ScatterPoint[]): { readonly min: number; readonly max: number } {
  if (points.length === 0) {
    return { min: 0, max: 1 };
  }
  const values = points.map((point) => point.x);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max(0.5, (max - min) * 0.08);
  return { min: Math.max(0, min - pad), max: max + pad };
}

function scaleX(value: number, domain: { readonly min: number; readonly max: number }): number {
  const width = WIDTH - PLOT.left - PLOT.right;
  const span = domain.max - domain.min;
  return PLOT.left + ((value - domain.min) / span) * width;
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
      return { anchor, lineY, labelY: Math.min(HEIGHT - PLOT.bottom - 8, lineY + index * 13 + 4) };
    });
}

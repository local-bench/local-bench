import { formatModularAxisProfile } from "@/components/local-intelligence-index";
import { VRAM_TIERS } from "@/lib/rig-match";
import { formatDuration, formatGb, formatScore } from "@/lib/format";
import type { AnchorReference } from "@/lib/data";
import type { ModelRun, Score } from "@/lib/schemas";

const WIDTH = 900;
const HEIGHT = 420;
const PLOT = {
  left: 62,
  right: 178,
  top: 28,
  bottom: 56,
} as const;
const Y_TICKS = [100, 75, 50, 25, 0] as const;

export type QualityVramRun = Omit<ModelRun, "composite"> & {
  readonly composite: Score;
  readonly point_href?: string;
  readonly point_kind?: QualityVramPointKind;
  readonly point_label?: string;
};

export type QualityVramPointKind = "this-model" | "family-finetune" | "base-model";

export type QualityVramLegendItem = {
  readonly kind: QualityVramPointKind;
  readonly label: string;
};

type ScatterPoint = {
  readonly run: QualityVramRun;
  readonly x: number;
};

export function QualityVramScatter({
  anchorRuns,
  ariaLabel,
  description,
  omittedLabel = "run(s) omitted from x-axis: no footprint",
  pointLegend = [],
  runs,
  showPointLabels = true,
  testId = "quality-vram-scatter",
  title,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly ariaLabel: string;
  readonly description: string;
  readonly omittedLabel?: string;
  readonly pointLegend?: readonly QualityVramLegendItem[];
  readonly runs: readonly QualityVramRun[];
  readonly showPointLabels?: boolean;
  readonly testId?: string;
  readonly title: string;
}) {
  const points = runs.map(toScatterPoint).filter(isScatterPoint);
  const xDomain = getXDomain(points);
  const omitted = runs.length - points.length;
  const anchors = layoutAnchors(anchorRuns);

  return (
    <section data-testid={testId} className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-bench-text">{title}</h2>
          <p className="text-sm text-bench-muted">{description}</p>
        </div>
        <div className="font-mono text-xs text-bench-muted">
          {omitted} {omittedLabel}
        </div>
      </div>
      <div className="overflow-x-auto">
        <svg role="group" aria-label={ariaLabel} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full min-w-[320px] sm:min-w-[760px]">
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
          {VRAM_TIERS.map((tier) => {
            if (tier < xDomain.min || tier > xDomain.max) {
              return null;
            }
            const x = scaleX(tier, xDomain);
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
                <text x={x + 4} y={PLOT.top + 14} className="fill-bench-muted-2" fontSize="11">
                  {tier}GB
                </text>
              </g>
            );
          })}
          <line x1={PLOT.left} x2={WIDTH - PLOT.right} y1={HEIGHT - PLOT.bottom} y2={HEIGHT - PLOT.bottom} className="stroke-bench-line-strong" />
          <line x1={PLOT.left} x2={PLOT.left} y1={PLOT.top} y2={HEIGHT - PLOT.bottom} className="stroke-bench-line-strong" />
          {anchors.map(({ anchor, lineY, labelY }) => (
            <g key={anchor.run_id}>
              <line x1={PLOT.left} x2={WIDTH - PLOT.right} y1={lineY} y2={lineY} className="stroke-bench-anchor" strokeDasharray="7 6" strokeWidth="1.5" />
              <text x={WIDTH - PLOT.right + 12} y={labelY} className="fill-bench-anchor-soft" fontSize="12">
                <tspan x={WIDTH - PLOT.right + 12}>{anchor.model_label} {formatScore(anchor.composite.point)}</tspan>
                <tspan x={WIDTH - PLOT.right + 12} dy="13">{formatModularAxisProfile(anchor.axes)}</tspan>
              </text>
            </g>
          ))}
          {points.map((point) => {
            const cx = scaleX(point.x, xDomain);
            const cy = scaleY(point.run.composite.point);
            const label = point.run.point_label ?? point.run.quant_label ?? point.run.run_id ?? "catalog shell";
            // Demo rows carry synthetic wall times, so only real measured runs show a bench time.
            const benchedIn =
              !point.run.demo && typeof point.run.wall_time_seconds === "number"
                ? `benched in ${formatDuration(point.run.wall_time_seconds)} · `
                : "";
            const tipLine1 = `${label} — ${formatScore(point.run.composite.point)}`;
            const tipLine2 = `${benchedIn}~${formatGb(point.run.vram_footprint_gb)} to run`;
            const tipWidth = Math.max(tipLine1.length, tipLine2.length) * 6.6 + 20;
            // Clamp the tooltip inside the plot; flip below the dot when it would clip the top.
            const tipX = Math.min(Math.max(cx - tipWidth / 2, 6), WIDTH - tipWidth - 6);
            const tipY = cy - 52 > 4 ? cy - 52 : cy + 14;
            const pointKind = point.run.point_kind ?? "this-model";
            const pointBody = (
              <>
                <title>{`${label}: ${formatScore(point.run.composite.point)} — ${tipLine2}`}</title>
                <circle cx={cx} cy={cy} r="14" fill="transparent" />
                <PointMarker cx={cx} cy={cy} demo={point.run.demo} kind={pointKind} />
                {showPointLabels ? (
                  <text x={cx + 10} y={cy - 10} className="fill-bench-text" fontSize="12">
                    {label}
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
              </>
            );
            return (
              // CSS-only hover (server component, no client JS): the tooltip group is toggled by
              // group-hover; the transparent r=14 circle is the hit target — the visible 6px dot
              // is too small to hover reliably.
              point.run.point_href === undefined ? (
                <g key={point.run.run_id ?? label} className="group">
                  {pointBody}
                </g>
              ) : (
                <a key={point.run.run_id ?? label} href={point.run.point_href} className="group">
                  {pointBody}
                </a>
              )
            );
          })}
          {points.length === 0 ? (
            <text x={(WIDTH - PLOT.right + PLOT.left) / 2} y={210} className="fill-bench-muted" fontSize="14" textAnchor="middle">
              No local runs include VRAM footprint yet.
            </text>
          ) : null}
          <text x={(WIDTH - PLOT.right + PLOT.left) / 2} y={HEIGHT - 18} className="fill-bench-muted" fontSize="12" textAnchor="middle">
            model memory footprint (GB)
          </text>
          <text x="18" y="210" className="fill-bench-muted" fontSize="12" textAnchor="middle" transform="rotate(-90 18 210)">
            index score
          </text>
          <text x={PLOT.left} y={HEIGHT - PLOT.bottom + 26} className="fill-bench-muted" fontSize="12">
            {formatGb(xDomain.min)}
          </text>
          <text x={WIDTH - PLOT.right} y={HEIGHT - PLOT.bottom + 26} className="fill-bench-muted" fontSize="12" textAnchor="end">
            {formatGb(xDomain.max)}
          </text>
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-bench-muted">
        {pointLegend.map((item) => (
          <span key={item.kind} className="inline-flex items-center gap-1.5">
            <LegendMarker kind={item.kind} />
            {item.label}
          </span>
        ))}
        <span>{anchors.length > 0 ? "Dashed horizontal lines are API frontier ceilings." : "Dashed vertical lines mark common VRAM tiers."}</span>
        <span className="text-bench-warn">Amber points are synthetic demo preview data.</span>
      </div>
    </section>
  );
}

function PointMarker({
  cx,
  cy,
  demo,
  kind,
}: {
  readonly cx: number;
  readonly cy: number;
  readonly demo: boolean;
  readonly kind: QualityVramPointKind;
}) {
  if (kind === "family-finetune") {
    return (
      <rect
        data-point-kind={kind}
        x={cx - 5}
        y={cy - 5}
        width="10"
        height="10"
        rx="1"
        className="fill-bench-anchor stroke-bench-bg"
        strokeWidth="2"
      />
    );
  }
  if (kind === "base-model") {
    return (
      <path
        data-point-kind={kind}
        d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy} L ${cx} ${cy + 7} L ${cx - 7} ${cy} Z`}
        className="fill-bench-mixed stroke-bench-bg"
        strokeWidth="2"
      />
    );
  }
  return (
    <circle
      data-point-kind={kind}
      cx={cx}
      cy={cy}
      r="6"
      className={demo ? "fill-bench-warn stroke-bench-bg" : "fill-bench-accent stroke-bench-bg"}
      strokeWidth="2"
    />
  );
}

function LegendMarker({ kind }: { readonly kind: QualityVramPointKind }) {
  if (kind === "family-finetune") {
    return <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-[1px] bg-bench-anchor" />;
  }
  if (kind === "base-model") {
    return <span aria-hidden className="inline-block h-2.5 w-2.5 rotate-45 bg-bench-mixed" />;
  }
  return <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full bg-bench-accent" />;
}

function toScatterPoint(run: QualityVramRun): ScatterPoint | null {
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
      return { anchor, lineY, labelY: Math.min(HEIGHT - PLOT.bottom - 22, lineY + index * 26 + 4) };
    });
}

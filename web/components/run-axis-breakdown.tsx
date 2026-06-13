import { presentAxes } from "@/lib/axis-config";
import { axisLabel, clampScore, formatCi, formatScore } from "@/lib/format";
import type { Axis, AxisScore, RunDetail } from "@/lib/schemas";

export function RunAxisBreakdown({ run }: { readonly run: RunDetail }) {
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">Axis breakdown</h2>
      <div className="mt-4 space-y-4">
        {presentAxes(run.axes).map(([axis, score]) => (
          <AxisWhisker
            key={axis}
            axis={axis}
            score={score}
            highlighted={axis === run.worst_axis.bench}
          />
        ))}
      </div>
    </section>
  );
}

function AxisWhisker({
  axis,
  score,
  highlighted,
}: {
  readonly axis: Axis;
  readonly score: AxisScore;
  readonly highlighted: boolean;
}) {
  const lo = clampScore(score.lo);
  const hi = clampScore(score.hi);
  const point = clampScore(score.point);
  return (
    <div className={highlighted ? "rounded-md border border-amber-300/35 bg-amber-300/[0.08] p-3" : "p-3"}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <div className="font-semibold text-bench-text">
            {axisLabel(axis)}
            {highlighted ? <span className="ml-2 text-xs uppercase text-amber-200">worst axis</span> : null}
          </div>
          <div className="text-xs text-bench-muted">
            n={score.n} · errors={score.n_errors} · no answer={score.n_no_answer}
          </div>
        </div>
        <div className="font-mono text-sm text-bench-text">
          {formatScore(score.point)} <span className="text-bench-muted">{formatCi(score)}</span>
        </div>
      </div>
      <div className="relative mt-3 h-7">
        <div className="absolute top-3 h-1 w-full rounded-full bg-white/10" />
        <div
          className="absolute top-2 h-3 rounded-full bg-bench-accent/25"
          style={{ left: `${lo}%`, width: `${Math.max(1, hi - lo)}%` }}
        />
        <div
          className="absolute top-0 h-7 w-1 rounded-full bg-bench-accent shadow-[0_0_14px_rgba(50,210,180,0.65)]"
          style={{ left: `${point}%` }}
        />
      </div>
    </div>
  );
}

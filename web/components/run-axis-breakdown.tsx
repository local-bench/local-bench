import { AXIS_CONFIG, isAxisKey } from "@/lib/axis-config";
import { axisLabel, clampScore, formatCi, formatScore } from "@/lib/format";
import type { Axis, AxisScore, RunDetail } from "@/lib/schemas";
import { hasCompleteSeason2Coverage, SEASON_2_DIAGNOSTICS } from "@/lib/scoring-seasons";

export function RunAxisBreakdown({ run }: { readonly run: RunDetail }) {
  // Canonical axis order first, then any extra measured axes outside the config. An axis
  // that wasn't measured (absent, or present with n=0) renders "— not measured" rather than
  // a fabricated number+bar.
  const season2 = hasCompleteSeason2Coverage(run);
  const canonicalAxes = season2 ? ["tool_use", "knowledge", "instruction", "coding", "math"] : AXIS_CONFIG.map((axis) => axis.key);
  const extraAxes = Object.keys(run.axes)
    .filter((axis) => !canonicalAxes.includes(axis) && (season2 || !isAxisKey(axis)))
    .sort();
  const axisKeys = [...canonicalAxes, ...extraAxes];
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">Axis breakdown</h2>
      <div className="mt-4 space-y-4">
        {axisKeys.map((axis) => {
          const score = run.axes[axis];
          return score === undefined || score.n === 0 ? (
            <NotMeasuredAxis key={axis} axis={axis} />
          ) : (
            <AxisWhisker key={axis} axis={axis} score={score} highlighted={axis === run.worst_axis.bench} />
          );
        })}
      </div>
      {season2 ? (
        <div className="mt-5 border-t border-bench-line pt-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-bench-muted">Diagnostics · unweighted</h3>
          <div className="mt-2 space-y-2">
            {SEASON_2_DIAGNOSTICS.map((diagnostic) => {
              const score = run.diagnostics?.[diagnostic.key]
                ?? run.axes[diagnostic.key]
                ?? run.axes[diagnostic.bench];
              return score === undefined || score.n === 0 ? (
                <NotMeasuredAxis key={diagnostic.key} axis={diagnostic.key} label={diagnostic.label} />
              ) : (
                <AxisWhisker
                  key={diagnostic.key}
                  axis={diagnostic.key}
                  label={diagnostic.label}
                  score={score}
                  highlighted={false}
                />
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function NotMeasuredAxis({ axis, label }: { readonly axis: Axis; readonly label?: string }) {
  return (
    <div className="p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="font-semibold text-bench-text">{label ?? axisLabel(axis)}</div>
        <div className="font-mono text-xs text-bench-muted">— not measured</div>
      </div>
    </div>
  );
}

function AxisWhisker({
  axis,
  score,
  highlighted,
  label,
}: {
  readonly axis: Axis;
  readonly score: AxisScore;
  readonly highlighted: boolean;
  readonly label?: string;
}) {
  const lo = clampScore(score.lo);
  const hi = clampScore(score.hi);
  const point = clampScore(score.point);
  return (
    <div className={highlighted ? "rounded-md border border-bench-warn/35 bg-bench-warn/[0.08] p-3" : "p-3"}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <div className="font-semibold text-bench-text">
            {label ?? axisLabel(axis)}
            {highlighted ? <span className="ml-2 text-xs uppercase text-bench-warn-soft">worst axis</span> : null}
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
          className="absolute top-0 h-7 w-1 rounded-full bg-bench-accent shadow-[0_0_14px_rgba(63,208,212,0.65)]"
          style={{ left: `${point}%` }}
        />
      </div>
    </div>
  );
}

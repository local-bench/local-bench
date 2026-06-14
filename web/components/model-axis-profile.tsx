import { DemoBadge } from "@/components/badges";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { clampScore, formatCi, formatScore } from "@/lib/format";
import type { ModelData } from "@/lib/data";

export function ModelAxisProfile({ model }: { readonly model: ModelData }) {
  const bestRun = [...model.runs].sort((left, right) => right.composite.point - left.composite.point)[0] ?? null;
  if (bestRun === null) {
    return null;
  }

  const rows = AXIS_CONFIG.flatMap((axis) => {
    const score = bestRun.axes[axis.key];
    return score === undefined ? [] : [{ axis, score }];
  });

  return (
    <section data-testid="model-axis-profile" className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Per-axis profile</p>
          <h2 className="mt-2 text-2xl font-semibold text-bench-text">Best measured run by axis</h2>
          <p className="mt-2 text-sm text-bench-muted">{bestRun.quant_label ?? bestRun.run_id}</p>
        </div>
        {bestRun.demo ? <DemoBadge /> : null}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        {rows.map(({ axis, score }) => (
          <div key={axis.key} className="rounded border border-bench-line bg-bench-panel-2/70 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-bench-text">{axis.label}</span>
              <span className="font-mono text-sm text-bench-text">
                {formatScore(score.point)} <span className="text-bench-muted">{formatCi(score)}</span>
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded bg-bench-bg">
              <div className="h-full bg-bench-accent" style={{ width: `${clampScore(score.point)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

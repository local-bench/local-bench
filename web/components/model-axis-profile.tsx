import { DemoBadge } from "@/components/badges";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { clampScore, formatCi, formatScore } from "@/lib/format";
import type { ModelData } from "@/lib/data";
import type { AxisScore } from "@/lib/schemas";
import { displayIndexVersion, headlineScoreForDisplay } from "@/lib/scoring-seasons";

export function ModelAxisProfile({ model }: { readonly model: ModelData }) {
  const measured = model.runs.filter((run) => headlineScoreForDisplay(run) !== null);
  const firstSeason = measured[0] === undefined ? null : displayIndexVersion(measured[0]);
  const bestRun = measured
    .filter((run) => displayIndexVersion(run) === firstSeason)
    .sort((left, right) => (headlineScoreForDisplay(right)?.point ?? 0) - (headlineScoreForDisplay(left)?.point ?? 0))[0] ?? null;
  if (bestRun === null) {
    return null;
  }

  return (
    <section data-testid="model-axis-profile" className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Per-axis profile</p>
          <h2 className="mt-2 text-2xl font-semibold text-bench-text">Best measured run by axis</h2>
          <p className="mt-2 text-sm text-bench-muted">{bestRun.quant_label ?? bestRun.run_id ?? "measured run"}</p>
        </div>
        {bestRun.demo ? <DemoBadge /> : null}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        {(bestRun.axes["tool_use"] === undefined
          ? AXIS_CONFIG
          : [
              { key: "tool_use", label: "Tool use", color: "#ffb627" },
              ...AXIS_CONFIG.filter((axis) => ["knowledge", "instruction", "coding", "math"].includes(axis.key)),
            ]).map((axis) => (
          <AxisProfileCard key={axis.key} label={axis.label} score={bestRun.axes[axis.key]} />
        ))}
      </div>
    </section>
  );
}

// An axis is "measured" only when it is present AND has a non-zero item count. Absent or
// n=0 axes (e.g. Math/Agentic on a Knowledge+Instruction-only run) render "— not measured",
// never a fabricated number+bar.
function AxisProfileCard({ label, score }: { readonly label: string; readonly score: AxisScore | undefined }) {
  if (score === undefined || score.n === 0) {
    return (
      <div className="rounded border border-bench-line bg-bench-panel-2/70 p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-bench-text">{label}</span>
          <span className="font-mono text-xs text-bench-muted">— not measured</span>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded border border-bench-line bg-bench-panel-2/70 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-bench-text">{label}</span>
        <span className="font-mono text-sm text-bench-text">
          {formatScore(score.point)} <span className="text-bench-muted">{formatCi(score)}</span>
        </span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded bg-bench-bg">
        <div className="h-full bg-bench-accent" style={{ width: `${clampScore(score.point)}%` }} />
      </div>
    </div>
  );
}

import { axisColor } from "@/lib/axis-config";
import type { AgenticModel, AxisScore } from "@/lib/schemas";

export const AGENTIC_COLUMN_TOOLTIP =
  "Agentic | AppWorld-C interactive API-coding success rate | 50% of the Local Intelligence Index";

export function formatAgenticPct(model: AgenticModel | undefined): string {
  if (model === undefined) {
    return "-";
  }
  return `${model.asr_pct.toFixed(1)}%`;
}

export function AgenticHeaderLabel() {
  return <span title={AGENTIC_COLUMN_TOOLTIP}>Agentic</span>;
}

export function AgenticCell({
  model,
  axisScore,
}: {
  readonly model: AgenticModel | undefined;
  // The row's own measured agentic axis. The funnel-history join (agentic.json) only covers
  // models with standalone AppWorld campaign files — a ranked run whose agentic verdicts live
  // inside its five-axis bundle (and any future community row) misses the join, so fall back
  // to the run's measured success rate rather than rendering an empty cell.
  readonly axisScore?: AxisScore | undefined;
}) {
  if (model === undefined && (axisScore === undefined || axisScore.n === 0)) {
    return <div className="min-w-[88px] font-mono text-xs text-bench-muted" title={AGENTIC_COLUMN_TOOLTIP}>-</div>;
  }
  const pctValue = model !== undefined ? model.asr_pct : (axisScore?.raw_accuracy ?? 0) * 100;
  const pct = Math.min(100, Math.max(0, pctValue));
  const detail =
    model !== undefined
      ? `${model.n_runs} run${model.n_runs === 1 ? "" : "s"} | ${model.n_tasks} tasks`
      : `${axisScore?.n ?? 0} tasks | ranked run`;
  return (
    <div className="min-w-[88px]" title={AGENTIC_COLUMN_TOOLTIP}>
      <div className="font-mono text-xs text-bench-text">{`${pctValue.toFixed(1)}%`}</div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: axisColor("agentic") }} />
      </div>
      <div className="mt-0.5 font-mono text-[10px] text-bench-muted">{detail}</div>
    </div>
  );
}

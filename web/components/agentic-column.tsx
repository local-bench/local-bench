import type { AgenticModel } from "@/lib/schemas";

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

export function AgenticCell({ model }: { readonly model: AgenticModel | undefined }) {
  if (model === undefined) {
    return <div className="min-w-[88px] font-mono text-xs text-bench-muted" title={AGENTIC_COLUMN_TOOLTIP}>-</div>;
  }
  const runs = `${model.n_runs} run${model.n_runs === 1 ? "" : "s"} | ${model.n_tasks} tasks`;
  const pct = Math.min(100, Math.max(0, model.asr_pct));
  return (
    <div className="min-w-[88px]" title={AGENTIC_COLUMN_TOOLTIP}>
      <div className="font-mono text-xs text-bench-text">{formatAgenticPct(model)}</div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-bench-accent/55" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-0.5 font-mono text-[10px] text-bench-muted">{runs}</div>
    </div>
  );
}

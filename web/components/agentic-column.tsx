import type { AgenticModel } from "@/lib/schemas";

// EXPERIMENTAL "Agentic" leaderboard column. Renders the AppWorld-C interactive API-coding ASR
// (success rate) from agentic.json, joined to each row by slug. It is a SEPARATE preview signal —
// 0% Local Intelligence Index weight, produced by a separate harness, NOT part of the frozen K+I
// board — and is never mixed into the headline Index. Both the full board (home-leaderboard) and
// the home best-variant table render the same header + cell from here so they stay identical.

// The full, explicit meaning of the column, surfaced as the header tooltip (native title) and the
// best-variant table's footnote so the experimental, non-Index status is unmissable.
export const AGENTIC_COLUMN_TOOLTIP =
  "Agentic · AppWorld-C interactive API-coding ASR · experimental · 0% Index weight · separate harness, not in the headline Index";

const AGENTIC_HEADER_SUBTITLE = "AppWorld-C ASR · exp · 0% Index";

// Percentage cell value for a row, e.g. "14.6%"; "—" when the model has no agentic run yet.
// One decimal place, matching the score columns' precision.
export function formatAgenticPct(model: AgenticModel | undefined): string {
  if (model === undefined) {
    return "—";
  }
  return `${model.asr_pct.toFixed(1)}%`;
}

// Header label matching the multi-line style of the Index header (title line + muted mono
// qualifier). The native title carries the full experimental/0%-weight explanation.
export function AgenticHeaderLabel() {
  return (
    <span className="flex flex-col gap-0.5 leading-tight" title={AGENTIC_COLUMN_TOOLTIP}>
      <span>Agentic</span>
      <span className="font-mono text-[10px] normal-case text-bench-muted">{AGENTIC_HEADER_SUBTITLE}</span>
    </span>
  );
}

// Body cell. Muted "—" when there is no agentic data for the row; otherwise a mini-bar matching the
// Knowledge/Instruction axis cells (number + thin fill + provenance) — but in a DISTINCT purple
// tone, not the cyan the Index axes use, so it reads as "measured, but not part of the Index."
export function AgenticCell({ model }: { readonly model: AgenticModel | undefined }) {
  if (model === undefined) {
    return <div className="min-w-[88px] font-mono text-xs text-bench-muted" title={AGENTIC_COLUMN_TOOLTIP}>—</div>;
  }
  const runs = `${model.n_runs} run${model.n_runs === 1 ? "" : "s"} · ${model.n_tasks} tasks`;
  const pct = Math.min(100, Math.max(0, model.asr_pct));
  return (
    <div className="min-w-[88px]" title={AGENTIC_COLUMN_TOOLTIP}>
      <div className="font-mono text-xs text-bench-text">{formatAgenticPct(model)}</div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-bench-purple/60" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-0.5 font-mono text-[10px] text-bench-muted">{runs}</div>
    </div>
  );
}

import type { ConformanceGate } from "@/lib/schemas";

type Props = {
  readonly gate: ConformanceGate | undefined;
  readonly showReason?: boolean;
  readonly compact?: boolean;
};

const BAND_CLASS: Record<ConformanceGate["band"], string> = {
  green: "border-bench-better/45 bg-bench-better/10 text-bench-better",
  amber: "border-bench-warn/45 bg-bench-warn/10 text-bench-warn",
  red: "border-red-400/45 bg-red-400/10 text-red-200",
};

export function ConformancePill({ gate, showReason = false, compact = false }: Props) {
  if (gate === undefined) {
    return (
      <span className="inline-flex min-w-[118px] rounded border border-bench-muted/30 bg-white/[0.03] px-2 py-1 font-mono text-[11px] uppercase text-bench-muted">
        not measured
      </span>
    );
  }

  const reason = dominantReason(gate);
  return (
    <span
      className={`inline-flex min-w-[142px] flex-col rounded border px-2 py-1 font-mono leading-tight ${BAND_CLASS[gate.band]}`}
      title={`${gate.label}: ${formatPercent(gate.pass_rate.point)}% [${formatPercent(gate.pass_rate.lo)}-${formatPercent(gate.pass_rate.hi)}], invalid JSON ${formatPercent(gate.invalid_json_rate)}%, n=${gate.n_items}`}
    >
      <span className="text-[10px] font-semibold uppercase">GATE {gate.band.toUpperCase()}</span>
      <span className={compact ? "text-[11px]" : "text-xs"}>
        {formatPercent(gate.pass_rate.point)}% [{formatPercent(gate.pass_rate.lo)}-{formatPercent(gate.pass_rate.hi)}]
      </span>
      {showReason ? <span className="mt-0.5 text-[10px] opacity-80">{reason}</span> : null}
    </span>
  );
}

function dominantReason(gate: ConformanceGate): string {
  const first = gate.band_reasons[0];
  if (first === "pass<60") {
    return "pass <60%";
  }
  return `invalid JSON ${formatPercent(gate.invalid_json_rate)}%`;
}

function formatPercent(value: number): string {
  return value.toFixed(1);
}

import { ModularAxisProfile } from "@/components/local-intelligence-index";
import { axisColor } from "@/lib/axis-config";
import { clampScore, formatCi, formatScore } from "@/lib/format";
import type { AxisScore, Score } from "@/lib/schemas";

export function ScoreBar({
  axes,
  score,
  tone = "accent",
  rail = false,
}: {
  readonly axes?: Readonly<Record<string, AxisScore>>;
  readonly score: Score;
  readonly tone?: "accent" | "anchor" | "muted";
  // Replace the single-color bar with the index-weighted contribution rail. Only valid where
  // the score IS the full Local Intelligence Index — the rail hardcodes index-v2.1 weights.
  readonly rail?: boolean;
}) {
  const barColor =
    tone === "anchor" ? "bg-bench-anchor" : tone === "muted" ? "bg-bench-muted" : "bg-bench-accent";
  return (
    <div className="min-w-[132px]">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold text-bench-text">{formatScore(score.point)}</span>
        <span className="font-mono text-xs text-bench-muted">{formatCi(score)}</span>
      </div>
      {rail && axes !== undefined ? (
        <IndexContributionRail axes={axes} className="mt-1 h-1.5 w-full" />
      ) : (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${clampScore(score.point)}%` }} />
        </div>
      )}
      {axes === undefined ? null : (
        <ModularAxisProfile axes={axes} className="mt-1 block font-mono text-[11px] text-bench-muted" />
      )}
    </div>
  );
}

// The Local Intelligence Index bar as its per-axis contributions, in the shared axis palette —
// the same rail the landing Leaderboard summary draws, so segments match axis columns everywhere.
// Hardcodes index-v2.1 headline weights; never use for the static (no-agentic) composite.
export function IndexContributionRail({
  axes,
  className,
}: {
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly className?: string;
}) {
  const a = (axes["agentic"]?.point ?? 0) * 0.5;
  const k = (axes["knowledge"]?.point ?? 0) * 0.15;
  const i = (axes["instruction"]?.point ?? 0) * 0.15;
  const t = (axes["tool_calling"]?.point ?? 0) * 0.1;
  const c = (axes["coding"]?.point ?? 0) * 0.1;
  const total = a + k + i + t + c;
  return (
    <div
      className={`flex overflow-hidden rounded-full bg-white/10 ${className ?? "h-1.5 w-full"}`}
      title={`Agentic ${a.toFixed(1)} + Knowledge ${k.toFixed(1)} + Instruction ${i.toFixed(1)} + Tool ${t.toFixed(1)} + Coding ${c.toFixed(1)} = ${total.toFixed(1)}`}
    >
      <div className="h-full" style={{ width: `${a}%`, backgroundColor: axisColor("agentic") }} />
      <div className="h-full" style={{ width: `${k}%`, backgroundColor: axisColor("knowledge") }} />
      <div className="h-full" style={{ width: `${i}%`, backgroundColor: axisColor("instruction") }} />
      <div className="h-full" style={{ width: `${t}%`, backgroundColor: axisColor("tool_calling") }} />
      <div className="h-full" style={{ width: `${c}%`, backgroundColor: axisColor("coding") }} />
    </div>
  );
}

export function AxisMiniBar({
  score,
  axis,
}: {
  readonly score: AxisScore | undefined;
  // Axis key selecting the shared axis color, so every mini bar matches the same axis's
  // segment in the index contribution rail. Omitted -> the neutral accent fill.
  readonly axis?: string;
}) {
  if (score === undefined || score.n === 0) {
    return <div className="min-w-[88px] font-mono text-xs text-bench-muted">n/a</div>;
  }
  return (
    <div className="min-w-[88px]">
      <div className="flex items-center justify-between gap-2 font-mono text-xs">
        <span className="text-bench-text">{formatScore(score.point)}</span>
        <span className="text-bench-muted">{formatCi(score)}</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full"
          style={{ width: `${clampScore(score.point)}%`, backgroundColor: axisColor(axis) }}
        />
      </div>
    </div>
  );
}

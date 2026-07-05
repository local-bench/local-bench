import { ModularAxisProfile } from "@/components/local-intelligence-index";
import { axisColor } from "@/lib/axis-config";
import { clampScore, formatCi, formatScore } from "@/lib/format";
import type { AxisScore, Score } from "@/lib/schemas";

export function ScoreBar({
  axes,
  score,
  tone = "accent",
}: {
  readonly axes?: Readonly<Record<string, AxisScore>>;
  readonly score: Score;
  readonly tone?: "accent" | "anchor" | "muted";
}) {
  const barColor =
    tone === "anchor" ? "bg-bench-anchor" : tone === "muted" ? "bg-bench-muted" : "bg-bench-accent";
  return (
    <div className="min-w-[132px]">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold text-bench-text">{formatScore(score.point)}</span>
        <span className="font-mono text-xs text-bench-muted">{formatCi(score)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${clampScore(score.point)}%` }} />
      </div>
      {axes === undefined ? null : (
        <ModularAxisProfile axes={axes} className="mt-1 block font-mono text-[11px] text-bench-muted" />
      )}
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

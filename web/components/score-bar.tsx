import { clampScore, formatCi, formatScore } from "@/lib/format";
import type { AxisScore, Score } from "@/lib/schemas";

export function ScoreBar({
  score,
  tone = "accent",
}: {
  readonly score: Score;
  readonly tone?: "accent" | "anchor" | "muted";
}) {
  const barColor =
    tone === "anchor" ? "bg-bench-anchor" : tone === "muted" ? "bg-zinc-400" : "bg-bench-accent";
  return (
    <div className="min-w-[132px]">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold text-bench-text">{formatScore(score.point)}</span>
        <span className="font-mono text-xs text-bench-muted">{formatCi(score)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${clampScore(score.point)}%` }} />
      </div>
    </div>
  );
}

export function AxisMiniBar({ score }: { readonly score: AxisScore | undefined }) {
  if (score === undefined) {
    return <div className="min-w-[88px] font-mono text-xs text-bench-muted">n/a</div>;
  }
  return (
    <div className="min-w-[88px]">
      <div className="flex items-center justify-between gap-2 font-mono text-xs">
        <span className="text-bench-text">{formatScore(score.point)}</span>
        <span className="text-bench-muted">{formatCi(score)}</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-bench-accent/55" style={{ width: `${clampScore(score.point)}%` }} />
      </div>
    </div>
  );
}

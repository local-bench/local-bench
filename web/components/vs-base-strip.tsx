import Link from "next/link";
import { axisLabel, formatScore } from "@/lib/format";
import type { VsBaseComparison } from "@/lib/vs-base";

export function VsBaseStrip({
  comparisons,
  label,
}: {
  readonly comparisons: readonly VsBaseComparison[];
  readonly label: "vs base" | "vs fine-tunes";
}) {
  if (comparisons.length === 0) {
    return null;
  }

  return (
    <section className="grid gap-3" aria-label={label}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">{label}</p>
          <h2 className="text-2xl font-semibold text-bench-text">Fine-tune comparison</h2>
        </div>
      </div>

      <div className="grid gap-3">
        {comparisons.map((comparison) => (
          <article
            key={`${comparison.derivative.catalogId}:${comparison.base.catalogId}`}
            className="rounded border border-bench-line bg-bench-panel p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-bench-text">{comparison.derivative.displayName}</h3>
                <p className="text-sm text-bench-muted">Fine-tune of {comparison.base.displayName}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {comparison.compositeDelta === null ? (
                  <span className="rounded border border-bench-line px-2 py-1 font-mono text-xs text-bench-muted">
                    composite n/a
                  </span>
                ) : (
                  <span
                    className={`rounded border px-2 py-1 font-mono text-xs ${deltaTone(comparison.compositeDelta)}`}
                  >
                    composite {formatDelta(comparison.compositeDelta)}
                  </span>
                )}
                <Link
                  href={comparison.compareHref}
                  className="rounded border border-bench-accent/50 px-2 py-1 font-mono text-xs uppercase text-bench-accent hover:border-bench-accent"
                >
                  compare to base
                </Link>
              </div>
            </div>

            {comparison.missing.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {comparison.missing.map((message) => (
                  <span
                    key={message}
                    className="rounded border border-bench-warn/40 bg-bench-warn/10 px-2 py-1 text-xs text-bench-warn-soft"
                  >
                    {message}
                  </span>
                ))}
              </div>
            ) : null}

            {comparison.axes.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-[640px] border-collapse text-sm">
                  <thead className="text-left text-xs uppercase tracking-wider text-bench-text/85">
                    <tr>
                      <th className="border-b border-bench-line px-3 py-2">Axis</th>
                      <th className="border-b border-bench-line px-3 py-2">Fine-tune</th>
                      <th className="border-b border-bench-line px-3 py-2">Base</th>
                      <th className="border-b border-bench-line px-3 py-2">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.axes.map((axis) => (
                      <tr key={axis.axis} className="border-b border-bench-line/70 last:border-b-0">
                        <td className="px-3 py-2 text-bench-muted">{axisLabel(axis.axis)}</td>
                        <td className="px-3 py-2 font-mono text-bench-text">{formatScore(axis.derivative.point)}</td>
                        <td className="px-3 py-2 font-mono text-bench-text">{formatScore(axis.base.point)}</td>
                        <td className={`px-3 py-2 font-mono ${deltaTextTone(axis.delta)}`}>{formatDelta(axis.delta)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm text-bench-muted">Measured axis deltas appear after both rows have board data.</p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function formatDelta(value: number): string {
  const formatted = formatScore(Math.abs(value));
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}

function deltaTone(value: number): string {
  if (Math.abs(value) < 0.05) {
    return "border-bench-line text-bench-tied";
  }
  return value > 0 ? "border-bench-better/50 text-bench-better" : "border-bench-worse/50 text-bench-worse";
}

function deltaTextTone(value: number): string {
  if (Math.abs(value) < 0.05) {
    return "text-bench-tied";
  }
  return value > 0 ? "text-bench-better" : "text-bench-worse";
}

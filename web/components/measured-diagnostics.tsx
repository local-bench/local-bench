import Link from "next/link";
import { DemoBadge } from "@/components/badges";
import { AxisMiniBar } from "@/components/score-bar";
import { axisLabel, presentAxes } from "@/lib/axis-config";
import type { AxisScore, IndexModel } from "@/lib/schemas";

export function MeasuredDiagnostics({ models }: { readonly models: readonly IndexModel[] }) {
  if (models.length === 0) {
    return null;
  }

  return (
    <section data-testid="measured-diagnostics" className="rounded-lg border border-bench-line bg-bench-panel/82">
      <div className="border-b border-bench-line px-4 py-4">
        <h2 className="text-lg font-semibold text-bench-text">Measured diagnostics</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Runs that measured only part of the headline scope (or ran outside it). Diagnostic only — never
          rank-comparable.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-[980px] border-collapse text-sm">
          <caption className="sr-only">Measured diagnostic rows excluded from ranked and static boards.</caption>
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3 font-semibold">Model</th>
              <th className="px-3 py-3 font-semibold">Lane</th>
              <th className="px-3 py-3 font-semibold">Tier</th>
              <th className="px-3 py-3 font-semibold">Measured axes</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.slug} className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
                <td className="px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                      {model.model_label}
                    </Link>
                    {model.demo ? <DemoBadge /> : null}
                  </div>
                  <div className="text-xs text-bench-muted">{model.family}</div>
                </td>
                <td className="px-3 py-3">
                  <MonoChip value={model.lane} />
                </td>
                <td className="px-3 py-3">
                  <MonoChip value={model.tier} />
                </td>
                <td className="px-3 py-3">
                  <AxisPoints axes={model.axes} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MonoChip({ value }: { readonly value: string | null }) {
  return (
    <span className="inline-flex rounded border border-bench-line bg-white/[0.03] px-2 py-1 font-mono text-[11px] uppercase text-bench-muted">
      {value ?? "n/a"}
    </span>
  );
}

function AxisPoints({ axes }: { readonly axes: Readonly<Record<string, AxisScore>> }) {
  const entries = presentAxes(axes);
  if (entries.length === 0) {
    return <span className="font-mono text-xs text-bench-muted">n/a</span>;
  }
  return (
    <div className="flex flex-wrap gap-3">
      {entries.map(([axis, score]) => (
        <div key={axis} className="min-w-[112px]">
          <div className="mb-1 font-mono text-[10px] uppercase text-bench-muted">{axisLabel(axis)}</div>
          <AxisMiniBar score={score} axis={axis} />
        </div>
      ))}
    </div>
  );
}

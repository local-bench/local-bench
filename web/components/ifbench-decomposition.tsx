import type { AxisScore } from "@/lib/schemas";

// Renders the IFBench instruction-following decomposition: Strict = Termination × Conditional.
// `raw_accuracy` IS the strict accuracy (the strict re-score counts non-terminating answers wrong).
// Shows a pending state until the strict-scored run JSONs are wired (the two fields are absent).
export function IfbenchDecomposition({ axis }: { readonly axis: AxisScore | undefined }) {
  if (axis?.termination_rate === undefined || axis.conditional_accuracy === undefined) {
    return (
      <section
        data-testid="ifbench-decomposition"
        className="rounded-lg border border-bench-line bg-bench-panel p-4"
      >
        <h3 className="text-sm font-semibold text-bench-text">Instruction-following decomposition</h3>
        <p className="mt-1 text-xs leading-5 text-bench-muted-2">
          Strict / termination / conditional breakdown is pending the strict-scored run data.
        </p>
      </section>
    );
  }

  return (
    <section data-testid="ifbench-decomposition" className="rounded-lg border border-bench-line bg-bench-panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-bench-text">Instruction-following decomposition</h3>
        <span className="font-mono text-xs text-bench-muted-2">Strict = Termination × Conditional</span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Stat label="Strict accuracy" percent={axis.raw_accuracy * 100} hint="correct AND terminated / all" emphasis />
        <Stat label="Termination rate" percent={axis.termination_rate * 100} hint="terminated / all" />
        <Stat label="Conditional accuracy" percent={axis.conditional_accuracy * 100} hint="correct / terminated" />
      </div>
      <p className="mt-3 max-w-3xl text-xs leading-5 text-bench-muted-2">
        Outputs that hit the answer-token cap are counted incorrect; this prevents non-terminating
        generations from getting credit for matching required tokens inside a runaway response.
      </p>
    </section>
  );
}

function Stat({
  label,
  percent,
  hint,
  emphasis = false,
}: {
  readonly label: string;
  readonly percent: number;
  readonly hint: string;
  readonly emphasis?: boolean;
}) {
  return (
    <div
      className={`rounded-md border p-3 ${emphasis ? "border-bench-accent/40 bg-bench-accent/[0.06]" : "border-bench-line bg-bench-panel-2/60"}`}
    >
      <div className="text-[11px] uppercase text-bench-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold ${emphasis ? "text-bench-accent" : "text-bench-text"}`}>
        {percent.toFixed(1)}%
      </div>
      <div className="mt-1 text-[11px] leading-4 text-bench-muted-2">{hint}</div>
    </div>
  );
}

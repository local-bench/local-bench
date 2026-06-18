import { QualityVramScatter } from "@/components/quality-vram-scatter";
import type { AnchorReference, ModelData } from "@/lib/data";

export function ModelScatter({
  model,
  anchorRuns,
}: {
  readonly model: ModelData;
  readonly anchorRuns: readonly AnchorReference[];
}) {
  const runs = model.runs.flatMap((run) =>
    run.composite === null
      ? []
      : [
          {
            ...run,
            composite: run.composite,
            point_label: run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell",
          },
      ],
  );

  if (runs.length === 0) {
    return (
      <section data-testid="model-scatter" className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">VRAM footprint vs composite</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
          Quality scatter appears after the first measured run attaches to this catalog model. Use the quant ladder above
          for current file size and VRAM requirements.
        </p>
      </section>
    );
  }

  return (
    <QualityVramScatter
      anchorRuns={anchorRuns}
      ariaLabel={`${model.model_label} composite scatter with anchor reference lines`}
      description="Where your run lands vs other quants and the frontier anchors."
      omittedLabel="run(s) listed below but omitted from scatter x: no footprint"
      runs={runs}
      title="VRAM footprint vs composite"
    />
  );
}

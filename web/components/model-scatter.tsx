import { QualityVramScatter } from "@/components/quality-vram-scatter";
import type { AnchorReference, ModelData } from "@/lib/data";

export function ModelScatter({
  model,
  anchorRuns,
}: {
  readonly model: ModelData;
  readonly anchorRuns: readonly AnchorReference[];
}) {
  const runs = model.runs.map((run) => ({
    ...run,
    point_label: run.quant_label ?? run.run_id.split("__").at(1) ?? run.run_id,
  }));

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

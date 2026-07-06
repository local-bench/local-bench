import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import { QualityVramScatter } from "@/components/quality-vram-scatter";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import type { AnchorReference, ModelData } from "@/lib/data";

export function ModelScatter({
  model,
  anchorRuns,
}: {
  readonly model: ModelData;
  readonly anchorRuns: readonly AnchorReference[];
}) {
  // Only current-index (headline lane) composites share a y-axis with the anchors. Legacy-lane
  // composites come from an earlier index version and would plot as false comparisons.
  const runs = model.runs.flatMap((run) =>
    run.composite === null || run.lane !== HEADLINE_LANE
      ? []
      : [
          {
            ...run,
            composite: run.composite,
            point_label: run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell",
          },
      ],
  );
  const legacyCount = model.runs.filter(
    (run) => run.composite !== null && run.lane !== HEADLINE_LANE,
  ).length;

  if (runs.length === 0) {
    return (
      <section data-testid="model-scatter" className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">VRAM footprint vs {LOCAL_INTELLIGENCE_INDEX_NAME}</h2>
        <p className="mt-1 font-mono text-xs text-bench-accent">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</p>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
          {legacyCount > 0
            ? `The scatter appears after this model's first current-index run lands. ${legacyCount} previous-index run${
                legacyCount === 1 ? " is" : "s are"
              } listed above as diagnostics but plot on a retired scale.`
            : "Intelligence Index scatter appears after the first measured run attaches to this catalog model. Use the quant ladder above for current file size and VRAM requirements."}
        </p>
      </section>
    );
  }

  return (
    <QualityVramScatter
      anchorRuns={anchorRuns}
      ariaLabel={`${model.model_label} ${LOCAL_INTELLIGENCE_INDEX_NAME} (${LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) scatter with anchor reference lines`}
      description={`${LOCAL_INTELLIGENCE_INDEX_QUALIFIER}. Where your run lands vs other quants and the frontier anchors.`}
      omittedLabel="run(s) listed below but omitted from scatter x: no footprint"
      runs={runs}
      title={`VRAM footprint vs ${LOCAL_INTELLIGENCE_INDEX_NAME}`}
    />
  );
}

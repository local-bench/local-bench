import { LOCAL_INTELLIGENCE_INDEX_NAME, LOCAL_INTELLIGENCE_INDEX_QUALIFIER } from "@/components/local-intelligence-index";
import {
  QualityVramScatter,
  type QualityVramLegendItem,
  type QualityVramPointKind,
  type QualityVramRun,
} from "@/components/quality-vram-scatter";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import type { AnchorReference, ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "@/lib/data";
import type { ModelRun } from "@/lib/schemas";

export function ModelScatter({
  model,
  anchorRuns,
  familyModels = [],
}: {
  readonly model: ModelDataWithConfiguredAxes;
  readonly anchorRuns: readonly AnchorReference[];
  readonly familyModels?: readonly ModelFamilyScatterModel[];
}) {
  // Only current-index (headline lane) composites share a y-axis with the anchors. Legacy-lane
  // composites come from an earlier index version and would plot as false comparisons.
  const ownRuns = model.runs.flatMap((run) =>
    toScatterRun(run, {
      label: run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell",
      pointKind: "this-model",
    }),
  );
  const familyRuns = familyModels.flatMap(({ model: familyModel, relation }) =>
    familyModel.runs.flatMap((run) =>
      toScatterRun(run, {
        label: `${familyModel.model_label} · ${run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell"}`,
        pointKind: relation,
      }),
    ),
  );
  const runs = [...ownRuns, ...familyRuns];
  const pointLegend: QualityVramLegendItem[] = [];
  if (ownRuns.length > 0) {
    pointLegend.push({ kind: "this-model", label: "This model" });
  }
  if (familyRuns.some((run) => run.point_kind === "family-finetune")) {
    pointLegend.push({ kind: "family-finetune", label: "Family fine-tunes" });
  }
  if (familyRuns.some((run) => run.point_kind === "base-model")) {
    pointLegend.push({ kind: "base-model", label: "Base model" });
  }
  const legacyCount = model.runs.filter(
    (run) =>
      run.score_status === "measured" &&
      run.lane !== HEADLINE_LANE &&
      run.diagnostic_composite !== null &&
      run.diagnostic_composite !== undefined,
  ).length;

  if (runs.length === 0) {
    return (
      <section data-testid="model-scatter" className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">VRAM footprint vs {LOCAL_INTELLIGENCE_INDEX_NAME}</h2>
        <p className="mt-1 font-mono text-xs text-bench-accent">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</p>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
          {legacyCount > 0
            ? `The scatter appears after this model's first current-index run lands. ${legacyCount} retired-lane diagnostic receipt${
                legacyCount === 1 ? " is" : "s are"
              } linked above but kept off this chart because the score uses a retired scale.`
            : "Intelligence Index scatter appears after the first measured run attaches to this catalog model. Use the quant ladder below for current file size and VRAM requirements."}
        </p>
      </section>
    );
  }

  return (
    <QualityVramScatter
      anchorRuns={anchorRuns}
      ariaLabel={`${model.model_label} ${LOCAL_INTELLIGENCE_INDEX_NAME} (${LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) scatter with anchor reference lines`}
      description={`${LOCAL_INTELLIGENCE_INDEX_QUALIFIER}. Where this model and current-lane family runs land vs the frontier anchors.`}
      omittedLabel="run(s) listed below but omitted from scatter x: no footprint"
      pointLegend={pointLegend}
      runs={runs}
      title={`VRAM footprint vs ${LOCAL_INTELLIGENCE_INDEX_NAME}`}
    />
  );
}

function toScatterRun(
  run: ModelRun,
  options: { readonly label: string; readonly pointKind: QualityVramPointKind },
): readonly QualityVramRun[] {
  if (run.composite === null || run.lane !== HEADLINE_LANE) {
    return [];
  }
  const pointBase = {
    ...run,
    composite: run.composite,
    point_kind: options.pointKind,
    point_label: options.label,
  };
  return run.run_id === null ? [pointBase] : [{ ...pointBase, point_href: `/run/${run.run_id}` }];
}

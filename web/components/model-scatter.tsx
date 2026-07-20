import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
  SEASON_2_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import {
  QualityVramScatter,
  type QualityVramLegendItem,
  type QualityVramPointKind,
  type QualityVramRun,
} from "@/components/quality-vram-scatter";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import type { AnchorReference, ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "@/lib/data";
import type { ModelRun } from "@/lib/schemas";
import { hasCompleteSeason2Coverage, INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

export function ModelScatter({
  model,
  anchorRuns,
  familyModels = [],
}: {
  readonly model: ModelDataWithConfiguredAxes;
  readonly anchorRuns: readonly AnchorReference[];
  readonly familyModels?: readonly ModelFamilyScatterModel[];
}) {
  // Season identity for the scale label: a run carrying the tool_use macro-axis is season-2
  // (same detection rule as indexQualifierForAxes). A model with only v3-axis runs keeps the v3
  // qualifier; a catalog shell with no measured axes gets the CURRENT index — its first run
  // will be scored there.
  const hasSeason2Run = model.runs.some((run) => run.axes["tool_use"] !== undefined);
  const hasSeason1Run = model.runs.some(
    (run) => run.axes["agentic"] !== undefined || run.axes["tool_calling"] !== undefined,
  );
  const indexQualifier = hasSeason2Run || !hasSeason1Run ? SEASON_2_INDEX_QUALIFIER : LOCAL_INTELLIGENCE_INDEX_QUALIFIER;
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
  if (runs.length === 0) {
    return (
      <section data-testid="model-scatter" className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">VRAM footprint vs {LOCAL_INTELLIGENCE_INDEX_NAME}</h2>
        <p className="mt-1 font-mono text-xs text-bench-accent">{indexQualifier}</p>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
          This chart appears after the model&apos;s first measured run lands. Use the quant ladder below for file size
          and VRAM requirements.
        </p>
      </section>
    );
  }

  return (
    <QualityVramScatter
      anchorRuns={anchorRuns}
      ariaLabel={`${model.model_label} ${LOCAL_INTELLIGENCE_INDEX_NAME} (${indexQualifier}) scatter with anchor reference lines`}
      description={`${indexQualifier}. Where this model and current-lane family runs land vs the frontier anchors.`}
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
  if (run.composite === null || run.lane !== HEADLINE_LANE || !isCompleteRun(run)) {
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

function isCompleteRun(run: ModelRun): boolean {
  if (run.index_version === INDEX_VERSION_V4) return hasCompleteSeason2Coverage(run);
  return ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => {
    const score = run.axes[axis];
    return score !== undefined && score.n > 0;
  });
}

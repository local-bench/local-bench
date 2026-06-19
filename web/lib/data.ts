import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { ZodType } from "zod";
import type { AxisKey } from "./axis-config";
import {
  IndexDataSchema,
  ModelDataSchema,
  RunDetailSchema,
  type AxisScore,
  type IndexData,
  type ModelData,
  type ModelRun,
  type RunDetail,
  type Score,
} from "./schemas";
import type { RigMatchAnchor, RigMatchCandidate } from "./rig-match";

const DATA_DIR = join(process.cwd(), "public", "data");

export type AnchorReference = {
  readonly axes: Record<string, AxisScore>;
  readonly model_label: string;
  readonly run_id: string;
  readonly composite: Score;
};

type AxisScoresWithConfiguredAxes = Record<string, AxisScore> & Record<AxisKey, AxisScore>;
type ModelRunWithConfiguredAxes = Omit<ModelRun, "axes"> & { readonly axes: AxisScoresWithConfiguredAxes };
type ModelDataWithConfiguredAxes = Omit<ModelData, "runs"> & { readonly runs: ModelRunWithConfiguredAxes[] };
type RunDetailWithConfiguredAxes = Omit<RunDetail, "axes"> & { readonly axes: AxisScoresWithConfiguredAxes };

export type ModelPageData = {
  readonly model: ModelDataWithConfiguredAxes;
  readonly anchorRuns: readonly AnchorReference[];
};

export type HomePageData = {
  readonly index: IndexData;
  readonly anchorRuns: readonly AnchorReference[];
  readonly rigAnchors: readonly RigMatchAnchor[];
  readonly rigCandidates: readonly RigMatchCandidate[];
};

export type ModelStaticParam = {
  readonly slug: string;
};

export type RunStaticParam = {
  readonly runId: string;
};

async function readJson<T>(segments: readonly string[], schema: ZodType<T>): Promise<T> {
  const file = await readFile(join(DATA_DIR, ...segments), "utf8");
  const parsed: unknown = JSON.parse(file);
  return schema.parse(parsed);
}

function sortByCompositeDesc(models: readonly IndexData["models"][number][]): IndexData["models"] {
  return [...models].sort(
    (left, right) =>
      nullableNumber(right.composite?.point, Number.NEGATIVE_INFINITY) -
        nullableNumber(left.composite?.point, Number.NEGATIVE_INFINITY) ||
      left.model_label.localeCompare(right.model_label),
  );
}

export async function getIndexData(): Promise<IndexData> {
  const index = await readJson(["index.json"], IndexDataSchema);
  return {
    ...index,
    models: sortByCompositeDesc(index.models),
  };
}

export async function getModelData(slug: string): Promise<ModelDataWithConfiguredAxes> {
  const model = await readJson(["models", `${slug}.json`], ModelDataSchema);
  return model as ModelDataWithConfiguredAxes;
}

export async function getRunData(runId: string): Promise<RunDetailWithConfiguredAxes> {
  const run = await readJson(["runs", `${runId}.json`], RunDetailSchema);
  return run as RunDetailWithConfiguredAxes;
}

type MeasuredModelRunWithConfiguredAxes = ModelRunWithConfiguredAxes & {
  readonly composite: Score;
  readonly run_id: string;
};

function isMeasuredConfiguredRun(run: ModelRunWithConfiguredAxes): run is MeasuredModelRunWithConfiguredAxes {
  return run.composite !== null && run.run_id !== null;
}

function toAnchorReference(model: ModelData, run: MeasuredModelRunWithConfiguredAxes): AnchorReference {
  return {
    axes: run.axes,
    model_label: model.model_label,
    run_id: run.run_id,
    composite: run.composite,
  };
}

async function getAnchorReferences(): Promise<readonly AnchorReference[]> {
  const index = await getIndexData();
  const anchorRows = index.models.filter((model) => model.kind === "anchor" && model.score_status === "measured");
  const anchorModels = await Promise.all(anchorRows.map((model) => getModelData(model.slug)));
  return anchorModels.flatMap((model) =>
    model.runs.filter(isMeasuredConfiguredRun).map((run) => toAnchorReference(model, run)),
  );
}

export async function getModelPageData(slug: string): Promise<ModelPageData> {
  const [model, anchorRuns] = await Promise.all([getModelData(slug), getAnchorReferences()]);
  return { model, anchorRuns };
}

export async function getHomePageData(): Promise<HomePageData> {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  const anchorRuns = models
    .filter((model) => model.kind === "anchor")
    .flatMap((model) =>
      model.runs.filter(isMeasuredConfiguredRun).map((run) => toAnchorReference(model, run)),
    );
  const rigAnchors = anchorRuns.map((anchor) => ({ modelLabel: anchor.model_label, score: anchor.composite }));
  const rigCandidates = models.flatMap((model) =>
    model.runs.map((run) => toRigMatchCandidate(model, run)),
  );
  return { anchorRuns, index, rigAnchors, rigCandidates };
}

export async function getModelStaticParams(): Promise<readonly ModelStaticParam[]> {
  const index = await getIndexData();
  return index.models.map((model) => ({ slug: model.slug }));
}

export async function getRunStaticParams(): Promise<readonly RunStaticParam[]> {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  return models.flatMap((model) =>
    model.runs.flatMap((run) => (run.run_id === null ? [] : [{ runId: run.run_id }])),
  );
}

function toRigMatchCandidate(model: ModelData, run: ModelRun): RigMatchCandidate {
  return {
    axes: run.axes,
    demo: model.demo || run.demo,
    family: model.family,
    kind: model.kind,
    lane: run.lane,
    modelLabel: model.model_label,
    modelSlug: model.slug,
    nItems: run.n_items,
    nRuns: model.runs.length,
    quantLabel: run.quant_label,
    runId: run.run_id,
    score: run.composite,
    scoreStatus: run.score_status,
    tokS: run.tok_s,
    vramFootprintGb: run.vram_footprint_gb,
    vramRequiredGb8k: run.vram_required_gb_8k ?? null,
  };
}

function nullableNumber(value: number | null | undefined, fallback: number): number {
  return value ?? fallback;
}

export { AXIS_KEYS as AXES } from "./axis-config";
export type {
  Axis,
  AxisScore,
  HardwareSummary,
  IndexModel,
  Kind,
  ModelData,
  ModelRun,
  PrimitiveRecord,
  RunDetail,
  RuntimeSummary,
  Score,
} from "./schemas";

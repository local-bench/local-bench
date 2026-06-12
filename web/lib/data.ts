import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { ZodType } from "zod";
import {
  IndexDataSchema,
  ModelDataSchema,
  RunDetailSchema,
  type IndexData,
  type ModelData,
  type ModelRun,
  type RunDetail,
  type Score,
} from "./schemas";

const DATA_DIR = join(process.cwd(), "public", "data");

export type AnchorReference = {
  readonly model_label: string;
  readonly run_id: string;
  readonly composite: Score;
};

export type ModelPageData = {
  readonly model: ModelData;
  readonly anchorRuns: readonly AnchorReference[];
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
  return [...models].sort((left, right) => right.composite.point - left.composite.point);
}

export async function getIndexData(): Promise<IndexData> {
  const index = await readJson(["index.json"], IndexDataSchema);
  return {
    ...index,
    models: sortByCompositeDesc(index.models),
  };
}

export async function getModelData(slug: string): Promise<ModelData> {
  return readJson(["models", `${slug}.json`], ModelDataSchema);
}

export async function getRunData(runId: string): Promise<RunDetail> {
  return readJson(["runs", `${runId}.json`], RunDetailSchema);
}

function toAnchorReference(model: ModelData, run: ModelRun): AnchorReference {
  return {
    model_label: model.model_label,
    run_id: run.run_id,
    composite: run.composite,
  };
}

async function getAnchorReferences(): Promise<readonly AnchorReference[]> {
  const index = await getIndexData();
  const anchorRows = index.models.filter((model) => model.kind === "anchor");
  const anchorModels = await Promise.all(anchorRows.map((model) => getModelData(model.slug)));
  return anchorModels.flatMap((model) =>
    model.runs.map((run) => toAnchorReference(model, run)),
  );
}

export async function getModelPageData(slug: string): Promise<ModelPageData> {
  const [model, anchorRuns] = await Promise.all([getModelData(slug), getAnchorReferences()]);
  return { model, anchorRuns };
}

export async function getModelStaticParams(): Promise<readonly ModelStaticParam[]> {
  const index = await getIndexData();
  return index.models.map((model) => ({ slug: model.slug }));
}

export async function getRunStaticParams(): Promise<readonly RunStaticParam[]> {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  return models.flatMap((model) => model.runs.map((run) => ({ runId: run.run_id })));
}

export { AXES } from "./schemas";
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

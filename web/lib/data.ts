import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { ZodType } from "zod";
import type { AxisKey } from "./axis-config";
import {
  AgenticDataSchema,
  CatalogSchema,
  IndexDataSchema,
  ModelDataSchema,
  RunDetailSchema,
  type AgenticData,
  type AgenticModel,
  type AxisScore,
  type CatalogModel,
  type IndexData,
  type IndexModel,
  type ModelData,
  type ModelRun,
  type RunDetail,
  type ScoreStatus,
  type Score,
} from "./schemas";
import {
  PartialCoverageDataSchema,
  partialCoverageRows,
  type BoardEntryRow,
} from "./board-entry";
import type { RigMatchAnchor, RigMatchCandidate } from "./rig-match";
import type { OnrampCatalogModel } from "./onramp";
import {
  buildVsBaseComparison,
  currentIndexRunId,
  type FineTuneComparePreset,
  type VsBaseBoardRow,
  type VsBaseComparison,
  type VsBaseSide,
} from "./vs-base";
import { HEADLINE_LANE } from "./leaderboard-score";

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
type RunDetailWithConfiguredAxes = Omit<RunDetail, "axes"> & {
  readonly axes: AxisScoresWithConfiguredAxes;
  readonly lane: string | null;
  readonly score_status: ScoreStatus;
};

export type ModelPageData = {
  readonly model: ModelDataWithConfiguredAxes;
  readonly anchorRuns: readonly AnchorReference[];
  readonly lineage: ModelLineage | null;
  readonly vsBaseComparisons: readonly VsBaseComparison[];
};

export type ModelLineage = {
  readonly baseModelId: string;
  readonly baseDisplayName: string;
  readonly baseSlug: string | null;
};

export type OnrampCatalog = {
  readonly models: readonly OnrampCatalogModel[];
  readonly popularityAsOf: string | null;
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

export async function getAgenticBySlug(): Promise<ReadonlyMap<string, AgenticModel>> {
  let data: AgenticData;
  try {
    data = await readJson(["agentic.json"], AgenticDataSchema);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return new Map();
    }
    throw error;
  }
  return new Map(Object.entries(data.models));
}

// Published partial-coverage submissions (unranked; measured a subset of headline axes). Reads a
// separate file so the frozen index.json anchor board is never touched; absent file => empty board.
export async function getPartialCoverageBoard(): Promise<readonly BoardEntryRow[]> {
  try {
    const data = await readJson(["partial-coverage.json"], PartialCoverageDataSchema);
    return partialCoverageRows(data);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

export async function getRunData(runId: string): Promise<RunDetailWithConfiguredAxes> {
  const run = await readJson(["runs", `${runId}.json`], RunDetailSchema);
  const model = await getModelData(modelSlugForRunId(runId));
  const modelRun = model.runs.find((candidate) => candidate.run_id === runId);
  return {
    ...run,
    lane: modelRun?.lane ?? run.manifest_summary.lane,
    score_status: modelRun?.score_status ?? "measured",
  } as RunDetailWithConfiguredAxes;
}

type CatalogFile = {
  readonly models: readonly CatalogModel[];
  readonly popularityAsOf: string | null;
};

async function getCatalogFile(): Promise<CatalogFile> {
  const file = await readFile(join(process.cwd(), "model_catalog.json"), "utf8");
  const parsed: unknown = JSON.parse(file);
  const catalog = CatalogSchema.parse(parsed);
  if (Array.isArray(catalog)) {
    return { models: catalog, popularityAsOf: null };
  }
  return { models: catalog.models, popularityAsOf: catalog.popularity_as_of };
}

function toOnrampModel(raw: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): OnrampCatalogModel {
  const paramsB =
    typeof raw.params_b === "number" ? raw.params_b : raw.params_b ? raw.params_b.total_b ?? null : null;
  const baseModelIds = catalogBaseIds(raw);
  const baseModelId = baseModelIds[0] ?? null;
  const base = baseModelId === null ? undefined : byId.get(baseModelId);
  return {
    id: raw.id,
    slug: raw.slug,
    displayName: raw.display_name,
    family: raw.family ?? "",
    org: raw.org ?? "",
    paramsB,
    reasoningCapable: raw.reasoning_capable ?? false,
    license: raw.license ?? "",
    ggufRepo: raw.gguf_repo ?? null,
    downloads: raw.popularity?.downloads ?? 0,
    likes: raw.popularity?.likes ?? 0,
    trending: raw.popularity?.trending ?? 0,
    modelKind: raw.model_kind,
    baseModelIds,
    baseModelId,
    baseModelSlug: base?.slug ?? null,
    baseModelDisplayName: base?.display_name ?? baseModelId,
    quants: raw.quants.map((quant) => ({
      label: quant.label,
      vramGb8k: quant.vram_gb_8k ?? null,
      fileGb: quant.file_gb ?? null,
      bpw: quant.bpw ?? null,
    })),
  };
}

function catalogBaseIds(entry: CatalogModel): readonly string[] {
  if (typeof entry.base_model === "string") {
    return [entry.base_model];
  }
  return entry.base_model ?? [];
}

function catalogBaseId(entry: CatalogModel): string | null {
  return catalogBaseIds(entry)[0] ?? null;
}

function isDerivativeCatalogEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): boolean {
  const baseModelId = catalogBaseId(entry);
  return entry.model_kind !== "base" || (baseModelId !== null && byId.has(baseModelId));
}

function boardRowForCatalogEntry(entry: CatalogModel, indexRows: readonly IndexModel[]): IndexModel | null {
  return indexRows.find((row) => row.catalog_id === entry.id || row.slug === entry.slug) ?? null;
}

function toVsBaseBoardRow(row: IndexModel | null): VsBaseBoardRow | null {
  if (row === null) {
    return null;
  }
  return {
    axes: row.axes,
    bestRunId: row.best_run_id,
    composite: row.composite,
    lane: row.lane,
    ranked: row.ranked,
    scoreStatus: row.score_status,
  };
}

function toVsBaseSide(entry: CatalogModel, indexRows: readonly IndexModel[]): VsBaseSide {
  return {
    catalogId: entry.id,
    displayName: entry.display_name,
    row: toVsBaseBoardRow(boardRowForCatalogEntry(entry, indexRows)),
    slug: entry.slug,
  };
}

function buildModelPageVsBaseComparisons({
  catalogEntry,
  catalogModels,
  indexRows,
  byId,
}: {
  readonly catalogEntry: CatalogModel | undefined;
  readonly catalogModels: readonly CatalogModel[];
  readonly indexRows: readonly IndexModel[];
  readonly byId: ReadonlyMap<string, CatalogModel>;
}): readonly VsBaseComparison[] {
  if (catalogEntry === undefined) {
    return [];
  }
  const baseModelId = catalogBaseId(catalogEntry);
  const base = baseModelId === null ? undefined : byId.get(baseModelId);
  if (base !== undefined && isDerivativeCatalogEntry(catalogEntry, byId)) {
    return [
      buildVsBaseComparison({
        base: toVsBaseSide(base, indexRows),
        derivative: toVsBaseSide(catalogEntry, indexRows),
      }),
    ];
  }

  return catalogModels
    .filter((entry) => catalogBaseId(entry) === catalogEntry.id && isDerivativeCatalogEntry(entry, byId))
    .map((derivative) =>
      buildVsBaseComparison({
        base: toVsBaseSide(catalogEntry, indexRows),
        derivative: toVsBaseSide(derivative, indexRows),
      }),
    );
}

// Reads model_catalog.json (one level above public/data) at build time and trims it to the fields the
// on-ramp picker needs. No build_data.py change required — the catalog already ships in the repo.
export async function getOnrampCatalog(): Promise<OnrampCatalog> {
  const catalog = await getCatalogFile();
  const byId = new Map(catalog.models.map((model) => [model.id, model]));
  return {
    models: catalog.models.filter((raw) => raw.quants.length > 0).map((raw) => toOnrampModel(raw, byId)),
    popularityAsOf: catalog.popularityAsOf,
  };
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
  const [model, anchorRuns, index, catalog] = await Promise.all([
    getModelData(slug),
    getAnchorReferences(),
    getIndexData(),
    getCatalogFile(),
  ]);
  const byId = new Map(catalog.models.map((entry) => [entry.id, entry]));
  const catalogEntry =
    catalog.models.find((entry) => entry.slug === slug) ??
    (model.catalog_id ? byId.get(model.catalog_id) : undefined);
  const baseModelId = catalogEntry === undefined ? null : catalogBaseId(catalogEntry);
  const base = baseModelId === null ? undefined : byId.get(baseModelId);
  const baseBoardRow =
    baseModelId === null
      ? undefined
      : index.models.find(
          (entry) => entry.catalog_id === baseModelId || (base?.slug !== undefined && entry.slug === base.slug),
        );
  const lineage =
    baseModelId === null
      ? null
      : {
          baseModelId,
          baseDisplayName: base?.display_name ?? baseModelId,
          baseSlug: base?.slug ?? baseBoardRow?.slug ?? null,
        };
  const vsBaseComparisons = buildModelPageVsBaseComparisons({
    catalogEntry,
    catalogModels: catalog.models,
    indexRows: index.models,
    byId,
  });
  return { model, anchorRuns, lineage, vsBaseComparisons };
}

export async function getFineTuneComparePresets(): Promise<readonly FineTuneComparePreset[]> {
  const [index, catalog] = await Promise.all([getIndexData(), getCatalogFile()]);
  const byId = new Map(catalog.models.map((entry) => [entry.id, entry]));
  return catalog.models.flatMap((entry) => {
    const baseModelId = catalogBaseId(entry);
    const base = baseModelId === null ? undefined : byId.get(baseModelId);
    if (base === undefined || !isDerivativeCatalogEntry(entry, byId)) {
      return [];
    }
    const comparison = buildVsBaseComparison({
      base: toVsBaseSide(base, index.models),
      derivative: toVsBaseSide(entry, index.models),
    });
    const leftRunId = currentIndexRunId(comparison.derivative.row);
    const rightRunId = currentIndexRunId(comparison.base.row);
    if (leftRunId === null || rightRunId === null) {
      return [];
    }
    return [{ slug: entry.slug, leftRunId, rightRunId }];
  });
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

export async function getSitemapRunStaticParams(): Promise<readonly RunStaticParam[]> {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  return models.flatMap((model) =>
    model.runs.flatMap((run) =>
      run.run_id !== null && run.score_status === "measured" && run.lane === HEADLINE_LANE
        ? [{ runId: run.run_id }]
        : [],
    ),
  );
}

function toRigMatchCandidate(model: ModelData, run: ModelRun): RigMatchCandidate {
  const candidate = {
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
    ranked: run.ranked,
    runId: run.run_id,
    score: run.composite,
    scoreStatus: run.score_status,
    tier: run.tier,
    tokS: run.tok_s,
    latencySMedian: run.latency_s_median ?? null,
    wallTimeSeconds: run.wall_time_seconds ?? null,
    vramFootprintGb: run.vram_footprint_gb,
    vramRequiredGb8k: run.vram_required_gb_8k ?? null,
  };
  return run.conformance_gates === undefined ? candidate : { ...candidate, conformanceGates: run.conformance_gates };
}

function nullableNumber(value: number | null | undefined, fallback: number): number {
  return value ?? fallback;
}

function modelSlugForRunId(runId: string): string {
  return runId.split("__")[0] ?? runId;
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

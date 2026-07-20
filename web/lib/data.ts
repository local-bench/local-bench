import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { z, type ZodType } from "zod";
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
  catalogBaseEntry,
  catalogBaseId,
  catalogBaseIds,
  catalogIsDerivativeEntry,
  catalogLineageFamilyEntries,
  catalogModelMap,
  type CatalogLineageRelation,
} from "./catalog-lineage";
import {
  buildVsBaseComparison,
  currentIndexRunId,
  type FineTuneComparePreset,
  type VsBaseBoardRow,
  type VsBaseComparison,
  type VsBaseSide,
} from "./vs-base";
import { HEADLINE_LANE } from "./leaderboard-score";
import { getCommunityBoardRows, type CommunityBoardRow } from "./community-data";
import { buildFamilyResolutionContext, resolveFamily } from "./family-resolution";
import { overlayLineageByArtifactSha } from "./overlay-lineage";
import { estimateRunVram } from "./model-run-metrics";

export {
  COMMUNITY_GROUP_PLACEHOLDER_ID,
  getCommunityGroup,
  getCommunityGroupStaticParams,
  getCommunityGroups,
  type CommunityGroupData,
} from "./community-data";

const DATA_DIR = join(process.cwd(), "public", "data");
// Keep this small list aligned with entries explicitly marked queued in docs/benchmark-queue.md.
const QUEUED_MODEL_SLUGS: ReadonlySet<string> = new Set([
  "bonsai-27b-ternary",
  "ornith-1-0-9b",
  "qwen3-5-9b",
]);

export type AnchorReference = {
  readonly axes: Record<string, AxisScore>;
  readonly model_label: string;
  readonly run_id: string;
  readonly composite: Score;
};

type AxisScoresWithConfiguredAxes = Record<string, AxisScore> & Record<AxisKey, AxisScore>;
type ModelRunWithConfiguredAxes = Omit<ModelRun, "axes"> & { readonly axes: AxisScoresWithConfiguredAxes };
export type ModelDataWithConfiguredAxes = Omit<ModelData, "runs"> & { readonly runs: ModelRunWithConfiguredAxes[] };
type RunDetailWithConfiguredAxes = Omit<RunDetail, "axes"> & {
  readonly axes: AxisScoresWithConfiguredAxes;
  readonly lane: string | null;
  readonly score_status: ScoreStatus;
};

export type ModelPageData = {
  readonly model: ModelDataWithConfiguredAxes;
  readonly anchorRuns: readonly AnchorReference[];
  readonly catalogOnly: boolean;
  readonly familyModels: readonly ModelFamilyScatterModel[];
  readonly lineage: ModelLineage | null;
  readonly queued: boolean;
  readonly vsBaseComparisons: readonly VsBaseComparison[];
};

export type ModelFamilyScatterRelation = CatalogLineageRelation;

export type ModelFamilyScatterModel = {
  readonly model: ModelDataWithConfiguredAxes;
  readonly relation: ModelFamilyScatterRelation;
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
  readonly catalogModels: readonly CatalogModel[];
  readonly communityCatalogModels: readonly IndexModelWithArtifacts[];
  readonly rigAnchors: readonly RigMatchAnchor[];
  readonly rigCandidates: readonly RigMatchCandidate[];
};

export type IndexModelWithArtifacts = IndexModel & {
  readonly artifactSha256s: readonly string[];
  readonly vramRequiredGb8k: number | null;
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

export async function getIndexModelsWithArtifacts(
  models: readonly IndexModel[],
): Promise<readonly IndexModelWithArtifacts[]> {
  const details = await Promise.all(models.map((model) => getModelData(model.slug)));
  return joinIndexModelArtifacts(models, details);
}

async function getModelDataIfExists(slug: string): Promise<ModelDataWithConfiguredAxes | null> {
  try {
    return await getModelData(slug);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

function catalogModelShell(entry: CatalogModel): ModelDataWithConfiguredAxes {
  return ModelDataSchema.parse({
    catalog_id: entry.id,
    demo: false,
    family: entry.family ?? entry.display_name,
    gguf_repo: entry.gguf_repo ?? null,
    kind: "community",
    license: entry.license ?? null,
    model_kind: entry.model_kind,
    model_label: entry.display_name,
    org: entry.org ?? null,
    runs: [],
    slug: entry.slug,
  }) as ModelDataWithConfiguredAxes;
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
      filename: quant.filename ?? null,
      revision: quant.revision ?? null,
      fileSha256: quant.file_sha256 ?? null,
      artifactFiles:
        quant.artifact_files?.map((artifact) => ({
          filename: artifact.filename,
          fileSha256: artifact.file_sha256,
        })) ?? [],
    })),
  };
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
    diagnosticComposite: row.diagnostic_composite ?? null,
    indexVersion: row.index_version,
    lane: row.lane,
    origin: row.origin,
    ranked: row.ranked,
    scoreStatus: row.score_status,
    trustLabel: row.trust_label,
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
  const base = catalogBaseEntry(catalogEntry, byId);
  if (base !== undefined && catalogIsDerivativeEntry(catalogEntry, byId)) {
    return [
      buildVsBaseComparison({
        base: toVsBaseSide(base, indexRows),
        derivative: toVsBaseSide(catalogEntry, indexRows),
      }),
    ];
  }

  return catalogModels
    .filter((entry) => catalogBaseId(entry) === catalogEntry.id && catalogIsDerivativeEntry(entry, byId))
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
  return run.composite !== null && run.run_id !== null && run.ranked && run.origin === "project_anchor" && run.trust_label === "project_anchor";
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

async function getModelFamilyScatterModels({
  byId,
  catalogEntry,
  catalogModels,
}: {
  readonly byId: ReadonlyMap<string, CatalogModel>;
  readonly catalogEntry: CatalogModel | undefined;
  readonly catalogModels: readonly CatalogModel[];
}): Promise<readonly ModelFamilyScatterModel[]> {
  if (catalogEntry === undefined) {
    return [];
  }
  const familyModels = await Promise.all(
    catalogLineageFamilyEntries({ byId, catalogEntry, catalogModels }).map(async ({ entry, relation }) => {
      const model = await getModelDataIfExists(entry.slug);
      return model === null ? null : { model, relation };
    }),
  );
  return familyModels.filter((entry): entry is ModelFamilyScatterModel => entry !== null);
}

export async function getModelPageData(slug: string): Promise<ModelPageData> {
  const [storedModel, anchorRuns, index, catalog] = await Promise.all([
    getModelDataIfExists(slug),
    getAnchorReferences(),
    getIndexData(),
    getCatalogFile(),
  ]);
  const byId = catalogModelMap(catalog.models);
  const catalogBySlug = catalog.models.find((entry) => entry.slug === slug);
  if (storedModel === null && catalogBySlug === undefined) {
    throw new Error(`model page data is unavailable for ${slug}`);
  }
  const model = storedModel ?? catalogModelShell(catalogBySlug as CatalogModel);
  const catalogEntry =
    catalogBySlug ??
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
  const familyModels = await getModelFamilyScatterModels({ byId, catalogEntry, catalogModels: catalog.models });
  return {
    model,
    anchorRuns,
    catalogOnly: storedModel === null,
    familyModels,
    lineage,
    queued: QUEUED_MODEL_SLUGS.has(slug),
    vsBaseComparisons,
  };
}

export async function getFineTuneComparePresets(): Promise<readonly FineTuneComparePreset[]> {
  const [index, catalog] = await Promise.all([getIndexData(), getCatalogFile()]);
  const byId = catalogModelMap(catalog.models);
  return catalog.models.flatMap((entry) => {
    const base = catalogBaseEntry(entry, byId);
    if (base === undefined || !catalogIsDerivativeEntry(entry, byId)) {
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
  const [index, catalog] = await Promise.all([getIndexData(), getCatalogFile()]);
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
  return {
    anchorRuns,
    catalogModels: catalog.models,
    communityCatalogModels: joinIndexModelArtifacts(index.models, models),
    index,
    rigAnchors,
    rigCandidates,
  };
}

function joinIndexModelArtifacts(
  indexModels: readonly IndexModel[],
  details: readonly ModelData[],
): readonly IndexModelWithArtifacts[] {
  const detailsBySlug = new Map(details.map((model) => [model.slug, model]));
  return indexModels.map((model) => {
    const detail = detailsBySlug.get(model.slug);
    const bestRun = detail?.runs.find((run) => run.run_id === model.best_run_id);
    return {
      ...model,
      artifactSha256s: detail?.artifacts?.map((artifact) => artifact.file_sha256) ?? [],
      vramRequiredGb8k: bestRun === undefined || detail === undefined
        ? null
        : estimateRunVram(bestRun, detail.runs)?.effectiveRequiredGb ?? null,
    };
  });
}

export async function getModelStaticParams(): Promise<readonly ModelStaticParam[]> {
  const [index, catalog, communityRows] = await Promise.all([
    getIndexData(),
    getCatalogFile(),
    getCommunityBoardRows(),
  ]);
  const indexSlugs = new Set(index.models.map((model) => model.slug));
  const communityBaseSlugs = communityBaseModelSlugs(communityRows ?? [], catalog.models, indexSlugs);
  return [
    ...index.models.map((model) => ({ slug: model.slug })),
    ...communityBaseSlugs.map((slug) => ({ slug })),
  ];
}

export function communityBaseModelSlugs(
  communityRows: readonly CommunityBoardRow[],
  catalogModels: readonly CatalogModel[],
  existingSlugs: ReadonlySet<string>,
): readonly string[] {
  const catalogById = new Map(catalogModels.map((model) => [model.id, model] as const));
  const resolutionContext = buildFamilyResolutionContext(
    catalogModels,
    [],
    overlayLineageByArtifactSha(),
  );
  const result = new Set<string>();
  for (const row of communityRows) {
    const resolution = resolveFamily(row, resolutionContext);
    for (const catalogId of resolution.chainCatalogIds) {
      const slug = catalogById.get(catalogId)?.slug;
      if (slug !== undefined && !existingSlugs.has(slug)) result.add(slug);
    }
  }
  return [...result].sort((left, right) => left.localeCompare(right));
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
    origin: run.origin,
    quantLabel: run.quant_label,
    ranked: run.ranked,
    trustLabel: run.trust_label,
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

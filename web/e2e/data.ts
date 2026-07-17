import { readFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

const DATA_DIR = path.join(process.cwd(), "public", "data");
export const HEADLINE_LANE = "bounded-final-v2";

const ScoreSchema = z
  .object({
    hi: z.number(),
    lo: z.number(),
    point: z.number(),
  })
  .passthrough();

const AxesSchema = z.record(z.string(), ScoreSchema);

const IndexModelSchema = z.object({
  axes: AxesSchema,
  best_run_id: z.string().nullable(),
  composite: ScoreSchema.nullable(),
  demo: z.boolean().optional(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  kind: z.enum(["anchor", "community", "maintainer_project"]),
  lane: z.string().nullable(),
  model_label: z.string(),
  origin: z.string().optional(),
  ranked: z.boolean(),
  score_status: z.string(),
  slug: z.string(),
  trust_label: z.string().optional(),
});

const IndexDataSchema = z.object({
  models: z.array(IndexModelSchema),
});

const ModelRunSchema = z.object({
  axes: AxesSchema,
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  lane: z.string().nullable(),
  origin: z.string().optional(),
  quant_label: z.string().nullable().optional(),
  ranked: z.boolean().optional(),
  run_id: z.string().nullable(),
  score_status: z.string(),
  trust_label: z.string().optional(),
});

const ModelDataSchema = z.object({
  catalog_id: z.string().nullable().optional(),
  kind: z.enum(["anchor", "community", "maintainer_project"]),
  model_label: z.string(),
  runs: z.array(ModelRunSchema),
  slug: z.string(),
});

// model_catalog.json entries — only the lineage fields the family-row derivation needs
// (mirrors CatalogModelSchema in web/lib/schemas.ts, incl. the model_kind "base" default).
const CatalogModelSchema = z
  .object({
    base_model: z.union([z.string(), z.array(z.string())]).nullable().optional(),
    id: z.string(),
    model_kind: z.string().optional().default("base"),
    slug: z.string(),
  })
  .passthrough();

const CatalogFileSchema = z.union([
  z.array(CatalogModelSchema),
  z.object({ models: z.array(CatalogModelSchema) }).passthrough(),
]);

type CatalogModel = z.infer<typeof CatalogModelSchema>;

const RunDataFileSchema = z.object({
  axes: AxesSchema,
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  lane: z.string().nullable().optional(),
  model_label: z.string(),
  ranked: z.boolean().optional(),
  run_id: z.string(),
  score_status: z.string().optional(),
});

export type Score = z.infer<typeof ScoreSchema>;
export type IndexModel = z.infer<typeof IndexModelSchema>;
export type ModelRun = z.infer<typeof ModelRunSchema>;
export type ModelData = z.infer<typeof ModelDataSchema>;
export type RunData = Omit<z.infer<typeof RunDataFileSchema>, "lane" | "score_status"> & {
  readonly lane: string | null;
  readonly score_status: string;
};
export type CompareRun = {
  readonly axes: Record<string, Score>;
  readonly composite: Score;
  readonly id: string;
  readonly lane: string | null;
  readonly modelLabel: string;
  readonly modelSlug: string;
  readonly quantLabel: string;
  readonly scoreScope: "current-index" | "previous-index";
};

export type StaticRoute = {
  readonly path: string;
  readonly screenshotName: string;
};

export async function readIndexData(): Promise<{ readonly models: readonly IndexModel[] }> {
  const json = await readJson(["index.json"]);
  return IndexDataSchema.parse(json);
}

export async function readModelData(slug: string): Promise<ModelData> {
  const json = await readJson(["models", `${slug}.json`]);
  return ModelDataSchema.parse(json);
}

export async function readRunData(runId: string): Promise<RunData> {
  const json = await readJson(["runs", `${runId}.json`]);
  const run = RunDataFileSchema.parse(json);
  const model = await readModelData(modelSlugForRunId(runId));
  const modelRun = model.runs.find((candidate) => candidate.run_id === runId);
  return {
    ...run,
    lane: modelRun?.lane ?? run.lane ?? null,
    score_status: modelRun?.score_status ?? run.score_status ?? "measured",
  };
}

export async function readCompareRuns(): Promise<readonly CompareRun[]> {
  const index = await readIndexData();
  const models = await Promise.all(index.models.map((model) => readModelData(model.slug)));
  return models
    .filter((model) => model.kind === "community")
    .flatMap((model) =>
      model.runs.flatMap((run) => {
        // Mirrors getCompareConfigs in web/lib/compare.ts: since 532c9b9 only the trusted
        // population is offered as a compare config (untrusted re-scored ladder runs are out).
        if (!isTrustedPopulation(run)) {
          return [];
        }
        const score = scoreForRun(run);
        if (
          run.run_id === null ||
          run.quant_label === null ||
          run.quant_label === undefined ||
          run.quant_label.trim() === "" ||
          score === null
        ) {
          return [];
        }
        return [
          {
            axes: run.axes,
            composite: score,
            id: run.run_id,
            lane: run.lane,
            modelLabel: model.model_label,
            modelSlug: model.slug,
            quantLabel: run.quant_label,
            scoreScope: scoreScopeForLane(run.lane),
          },
        ];
      }),
    )
    .sort(compareRuns);
}

// Mirrors web/lib/trusted-population.ts (532c9b9 "isolate trusted ranking population"):
// only the project-anchor population may affect ranks, representatives, or provenance.
export function isTrustedPopulation(row: { readonly origin?: string; readonly trust_label?: string }): boolean {
  return row.origin === "project_anchor" && row.trust_label === "project_anchor";
}

export function isTrustedRankedPopulation(row: {
  readonly origin?: string;
  readonly ranked?: boolean;
  readonly trust_label?: string;
}): boolean {
  return row.ranked === true && isTrustedPopulation(row);
}

export function rankedCurrentModels(models: readonly IndexModel[]): readonly IndexModel[] {
  // Mirrors isFullIndexRow in web/lib/leaderboard-score.ts: since 532c9b9 the ranked board
  // additionally gates rows through the trusted ranked population.
  return models.filter(
    (model) =>
      model.score_status === "measured" &&
      isTrustedRankedPopulation(model) &&
      model.lane === HEADLINE_LANE &&
      model.demo !== true &&
      model.composite !== null,
  );
}

export function retiredDiagnosticModels(models: readonly IndexModel[]): readonly IndexModel[] {
  return models.filter((model) => model.score_status === "measured" && model.lane !== HEADLINE_LANE);
}

export function runIds(runs: readonly ModelRun[]): readonly string[] {
  return runs.flatMap((run) => (run.run_id === null ? [] : [run.run_id]));
}

// Family variant rows on model pages (467b9e8 "show family variant profiles"): the variant
// board also lists lineage-related models' runs, each with its own /run receipt link, gated
// to measured headline-lane trusted-ranked runs (components/model-variant-board.tsx, f54ea9d).
// The lineage walk mirrors catalogLineageFamilyEntries in web/lib/catalog-lineage.ts.
export async function familyReceiptRunIds(slug: string): Promise<readonly string[]> {
  const catalogModels = await readCatalogModels();
  const byId = new Map(catalogModels.map((entry) => [entry.id, entry]));
  const model = await readModelData(slug);
  const catalogEntry =
    catalogModels.find((entry) => entry.slug === slug) ??
    (model.catalog_id === null || model.catalog_id === undefined ? undefined : byId.get(model.catalog_id));
  if (catalogEntry === undefined) {
    return [];
  }
  const familySlugs = lineageFamilyEntries(catalogEntry, catalogModels, byId).map((entry) => entry.slug);
  const ids: string[] = [];
  for (const familySlug of familySlugs) {
    const familyModel = await readModelData(familySlug);
    for (const run of familyModel.runs) {
      // Family rows render only measured headline-lane trusted-ranked runs; the receipt
      // link additionally needs a run id and a displayable composite.
      if (
        run.score_status === "measured" &&
        run.lane === HEADLINE_LANE &&
        isTrustedRankedPopulation(run) &&
        run.run_id !== null &&
        run.composite !== null
      ) {
        ids.push(run.run_id);
      }
    }
  }
  return ids;
}

async function readCatalogModels(): Promise<readonly CatalogModel[]> {
  // Same source the site reads at build time (getCatalogFile in web/lib/data.ts):
  // model_catalog.json sits one level above public/data.
  const contents = await readFile(path.join(process.cwd(), "model_catalog.json"), "utf8");
  const parsed = CatalogFileSchema.parse(JSON.parse(contents));
  return Array.isArray(parsed) ? parsed : parsed.models;
}

function catalogBaseIds(entry: CatalogModel): readonly string[] {
  if (typeof entry.base_model === "string") {
    return [entry.base_model];
  }
  return entry.base_model ?? [];
}

function catalogBaseEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): CatalogModel | undefined {
  const baseId = catalogBaseIds(entry)[0] ?? null;
  return baseId === null ? undefined : byId.get(baseId);
}

function catalogIsDerivativeEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): boolean {
  return entry.model_kind !== "base" || catalogBaseEntry(entry, byId) !== undefined;
}

function catalogRootEntry(entry: CatalogModel, byId: ReadonlyMap<string, CatalogModel>): CatalogModel {
  const visited = new Set<string>([entry.id]);
  let current = entry;
  while (true) {
    const baseId = catalogBaseIds(current)[0] ?? null;
    if (baseId === null) {
      return current;
    }
    const base = byId.get(baseId);
    if (base === undefined || visited.has(base.id)) {
      return current;
    }
    visited.add(base.id);
    current = base;
  }
}

function catalogDescendsFrom(
  entry: CatalogModel,
  ancestorId: string,
  byId: ReadonlyMap<string, CatalogModel>,
  visited: Set<string> = new Set([entry.id]),
): boolean {
  for (const baseId of catalogBaseIds(entry)) {
    if (baseId === ancestorId) {
      return true;
    }
    const base = byId.get(baseId);
    if (base !== undefined && !visited.has(base.id)) {
      visited.add(base.id);
      if (catalogDescendsFrom(base, ancestorId, byId, visited)) {
        return true;
      }
    }
  }
  return false;
}

function lineageFamilyEntries(
  catalogEntry: CatalogModel,
  catalogModels: readonly CatalogModel[],
  byId: ReadonlyMap<string, CatalogModel>,
): readonly CatalogModel[] {
  const base = catalogBaseEntry(catalogEntry, byId);
  if (base !== undefined && catalogIsDerivativeEntry(catalogEntry, byId)) {
    const root = catalogRootEntry(catalogEntry, byId);
    return root.id === catalogEntry.id ? [] : [root];
  }
  return catalogModels.filter(
    (entry) =>
      entry.id !== catalogEntry.id &&
      catalogDescendsFrom(entry, catalogEntry.id, byId) &&
      catalogIsDerivativeEntry(entry, byId),
  );
}

export function scoreForRun(run: ModelRun): Score | null {
  if (run.lane === HEADLINE_LANE) {
    return run.composite;
  }
  return run.diagnostic_composite ?? run.composite;
}

export async function getAllStaticRoutes(): Promise<readonly StaticRoute[]> {
  const index = await readIndexData();
  const models = await Promise.all(index.models.map((model) => readModelData(model.slug)));
  const contentRoutes: readonly StaticRoute[] = [
    { path: "/", screenshotName: "route-home" },
    { path: "/leaderboard", screenshotName: "route-leaderboard" },
    { path: "/compare", screenshotName: "route-compare" },
    { path: "/methodology", screenshotName: "route-methodology" },
  ];
  const modelRoutes = index.models.map((model) => ({
    path: `/model/${model.slug}/`,
    screenshotName: `route-model-${model.slug}`,
  }));
  const runRoutes = models.flatMap((model) =>
    model.runs.flatMap((run) =>
      run.run_id === null
        ? []
        : [
            {
              path: `/run/${run.run_id}/`,
              screenshotName: `route-run-${run.run_id}`,
            },
          ],
    ),
  );

  return [...contentRoutes, ...modelRoutes, ...runRoutes];
}

async function readJson(segments: readonly string[]): Promise<unknown> {
  const contents = await readFile(path.join(DATA_DIR, ...segments), "utf8");
  return JSON.parse(contents);
}

function compareRuns(left: CompareRun, right: CompareRun): number {
  return (
    scopeRank(left) - scopeRank(right) ||
    right.composite.point - left.composite.point ||
    left.modelLabel.localeCompare(right.modelLabel) ||
    left.quantLabel.localeCompare(right.quantLabel)
  );
}

function scopeRank(run: CompareRun): number {
  return run.scoreScope === "current-index" ? 0 : 1;
}

function scoreScopeForLane(lane: string | null): CompareRun["scoreScope"] {
  return lane === HEADLINE_LANE ? "current-index" : "previous-index";
}

function modelSlugForRunId(runId: string): string {
  const [slug] = runId.split("__");
  return slug ?? runId;
}

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
  ranked: z.boolean(),
  score_status: z.string(),
  slug: z.string(),
});

const IndexDataSchema = z.object({
  models: z.array(IndexModelSchema),
});

const ModelRunSchema = z.object({
  axes: AxesSchema,
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  lane: z.string().nullable(),
  quant_label: z.string().nullable().optional(),
  ranked: z.boolean().optional(),
  run_id: z.string().nullable(),
  score_status: z.string(),
});

const ModelDataSchema = z.object({
  kind: z.enum(["anchor", "community", "maintainer_project"]),
  model_label: z.string(),
  runs: z.array(ModelRunSchema),
  slug: z.string(),
});

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
        const score = scoreForRun(run);
        if (run.run_id === null || run.quant_label === null || run.quant_label === undefined || score === null) {
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

export function rankedCurrentModels(models: readonly IndexModel[]): readonly IndexModel[] {
  return models.filter(
    (model) =>
      model.score_status === "measured" &&
      model.ranked &&
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

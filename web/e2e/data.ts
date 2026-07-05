import { readFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

const DATA_DIR = path.join(process.cwd(), "public", "data");

const ScoreSchema = z.object({
  hi: z.number(),
  lo: z.number(),
  point: z.number(),
});

const IndexModelSchema = z.object({
  best_run_id: z.string(),
  composite: ScoreSchema,
  kind: z.enum(["anchor", "community"]),
  model_label: z.string(),
  slug: z.string(),
});

const IndexDataSchema = z.object({
  models: z.array(IndexModelSchema),
});

const ModelRunSchema = z.object({
  run_id: z.string(),
});

const ModelDataSchema = z.object({
  model_label: z.string(),
  runs: z.array(ModelRunSchema),
  slug: z.string(),
});

export type IndexModel = z.infer<typeof IndexModelSchema>;
export type ModelData = z.infer<typeof ModelDataSchema>;
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
    model.runs.map((run) => ({
      path: `/run/${run.run_id}/`,
      screenshotName: `route-run-${run.run_id}`,
    })),
  );

  return [...contentRoutes, ...modelRoutes, ...runRoutes];
}

async function readJson(segments: readonly string[]): Promise<unknown> {
  const contents = await readFile(path.join(DATA_DIR, ...segments), "utf8");
  return JSON.parse(contents);
}

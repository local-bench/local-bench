import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Reads the generated static data directly and enforces the launch invariants. On the scoreless
// catalog these pass vacuously (no ranked-measured rows); the moment the campaign ladder is wired
// they catch a model that is ranked+measured but missing/inconsistent. (Oracle integrity gate.)
const DATA_DIR = join(process.cwd(), "public", "data");

type IndexModel = {
  readonly slug: string;
  readonly best_run_id: string | null;
  readonly composite: { readonly point: number } | null;
  readonly ranked: boolean;
  readonly demo?: boolean;
  readonly score_status?: string;
  readonly axes: Record<string, unknown>;
};

function readJson<T>(...segments: string[]): T {
  return JSON.parse(readFileSync(join(DATA_DIR, ...segments), "utf8")) as T;
}

const index = readJson<{ readonly models: readonly IndexModel[] }>("index.json");
const rankedMeasured = index.models.filter(
  (model) => model.score_status === "measured" && model.ranked && model.demo !== true && model.composite !== null,
);

describe("public/data integrity — ranked measured rows", () => {
  it("every ranked measured model has a best_run_id that resolves to a non-null-composite run", () => {
    for (const model of rankedMeasured) {
      expect(model.best_run_id, `${model.slug} best_run_id`).not.toBeNull();
      const detail = readJson<{ readonly runs: readonly { readonly run_id: string | null; readonly composite: unknown }[] }>(
        "models",
        `${model.slug}.json`,
      );
      const run = detail.runs.find((entry) => entry.run_id === model.best_run_id);
      expect(run, `${model.slug} best run ${model.best_run_id ?? "null"}`).toBeDefined();
      expect(run?.composite, `${model.slug} best-run composite`).not.toBeNull();
    }
  });

  it("ranked measured rows are non-demo with a non-null composite and an axes object", () => {
    for (const model of rankedMeasured) {
      expect(model.demo ?? false, `${model.slug} demo`).toBe(false);
      expect(model.composite, `${model.slug} composite`).not.toBeNull();
      expect(typeof model.axes === "object" && model.axes !== null, `${model.slug} axes`).toBe(true);
    }
  });
});

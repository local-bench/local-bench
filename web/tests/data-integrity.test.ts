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
  readonly diagnostic_composite?: { readonly point: number } | null;
  readonly ranked: boolean;
  readonly demo?: boolean;
  readonly score_status?: string;
  readonly lane: string | null;
  readonly axes: Record<string, unknown>;
};

type RunReceipt = {
  readonly composite: { readonly point: number } | null;
  readonly diagnostic_composite?: { readonly point: number } | null;
  readonly lane?: string | null;
  readonly score_status?: string;
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

  it("IFBench decomposition (where present) satisfies strict ≈ termination × conditional", () => {
    for (const model of index.models) {
      const axis = (model.axes as Record<string, { raw_accuracy?: number; termination_rate?: number; conditional_accuracy?: number }>)[
        "instruction"
      ];
      if (axis?.termination_rate !== undefined && axis.conditional_accuracy !== undefined && axis.raw_accuracy !== undefined) {
        expect(
          Math.abs(axis.raw_accuracy - axis.termination_rate * axis.conditional_accuracy),
          `${model.slug} strict=termination×conditional`,
        ).toBeLessThan(0.01);
      }
    }
  });

  it("keeps retired-lane composites out of the standard index score field", () => {
    // Given generated index rows that include measured previous-index diagnostics.
    const legacyMeasured = index.models.filter(
      (model) => model.score_status === "measured" && model.lane !== "bounded-final-v2",
    );

    // When the public data is inspected through the index contract.
    const rowsWithStandardComposite = legacyMeasured.filter((model) => model.composite !== null);

    // Then every retired-lane score is quarantined under diagnostic_composite.
    expect(legacyMeasured).toHaveLength(6);
    expect(rowsWithStandardComposite).toEqual([]);
    expect(legacyMeasured.every((model) => model.diagnostic_composite !== null)).toBe(true);
    expect(legacyMeasured.every((model) => model.diagnostic_composite !== undefined)).toBe(true);
  });

  it("keeps retired-lane composites out of the standard run receipt score field", () => {
    const legacyMeasured = index.models.filter(
      (model) => model.score_status === "measured" && model.lane !== "bounded-final-v2",
    );

    for (const model of legacyMeasured) {
      expect(model.best_run_id, `${model.slug} best_run_id`).not.toBeNull();
      const receipt = readJson<RunReceipt>("runs", `${model.best_run_id ?? ""}.json`);
      expect(receipt.composite, `${model.slug} receipt composite`).toBeNull();
      expect(receipt.diagnostic_composite?.point, `${model.slug} receipt diagnostic_composite`).toBeCloseTo(
        model.diagnostic_composite?.point ?? Number.NaN,
        8,
      );
      expect(receipt.lane, `${model.slug} receipt lane`).toBe(model.lane);
      expect(receipt.score_status, `${model.slug} receipt score_status`).toBe("measured");
    }
  });
});

import { describe, expect, it } from "vitest";
import { selectBestVariantPoints } from "../lib/best-variant";
import { buildFamilyResolutionContext } from "../lib/family-resolution";
import { selectLandingBestPerBase } from "../lib/landing-best-per-base";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import type { RigMatchCandidate } from "../lib/rig-match";
import { IndexModelSchema, type CatalogModel, type IndexModel } from "../lib/schemas";

const AXIS_SCORE = {
  hi: 50,
  lo: 40,
  n: 100,
  n_errors: 0,
  n_no_answer: 0,
  point: 45,
  raw_accuracy: 0.45,
} as const;

describe("landing best-per-family selection", () => {
  it("keeps the base when its fine-tune scores lower", () => {
    const baseCatalog = catalogModel("Qwen/Qwen3.6-27B", "qwen3-6-27b", "Qwen3.6 27B");
    const fineTuneCatalog = catalogModel("Tune/Qwopus", "qwopus-27b", "Qwopus 27B", baseCatalog.id);
    const context = buildFamilyResolutionContext([baseCatalog, fineTuneCatalog]);
    const base = model(baseCatalog, 44.4);
    const fineTune = model(fineTuneCatalog, 43.3);

    const selected = selectLandingBestPerBase([base, fineTune], context);

    expect(selected.map((row) => row.slug)).toEqual([base.slug]);
  });

  it("keeps the fine-tune when it scores higher than its base", () => {
    const baseCatalog = catalogModel("Qwen/Qwen3.6-27B", "qwen3-6-27b", "Qwen3.6 27B");
    const fineTuneCatalog = catalogModel("Tune/Qwopus", "qwopus-27b", "Qwopus 27B", baseCatalog.id);
    const context = buildFamilyResolutionContext([baseCatalog, fineTuneCatalog]);
    const base = model(baseCatalog, 44.4);
    const fineTune = model(fineTuneCatalog, 46.1);

    const selected = selectLandingBestPerBase([base, fineTune], context);

    expect(selected.map((row) => row.slug)).toEqual([fineTune.slug]);
  });

  it("keeps same-family models that have different catalog roots", () => {
    const denseCatalog = catalogModel("Qwen/Qwen3.6-27B", "qwen3-6-27b", "Qwen3.6 27B");
    const moeCatalog = catalogModel("Qwen/Qwen3.6-35B-A3B", "qwen3-6-35b-a3b", "Qwen3.6 35B A3B");
    const context = buildFamilyResolutionContext([denseCatalog, moeCatalog]);
    const dense = model(denseCatalog, 44.4);
    const moe = model(moeCatalog, 45.2);

    const selected = selectLandingBestPerBase([dense, moe], context);

    expect(selected.map((row) => row.slug)).toEqual([dense.slug, moe.slug]);
  });

  it("keeps the replication panel population equal to the ranked table population", () => {
    // Given: a base and lower-scoring fine-tune are available to both landing selectors.
    const baseCatalog = catalogModel("Qwen/Qwen3.6-27B", "qwen3-6-27b", "Qwen3.6 27B");
    const fineTuneCatalog = catalogModel("Jackrong/Qwopus", "qwopus-27b", "Qwopus 27B", baseCatalog.id);
    const catalog = [baseCatalog, fineTuneCatalog];
    const context = buildFamilyResolutionContext(catalog);
    const models = [model(baseCatalog, 46.38), model(fineTuneCatalog, 45.12)];

    // When: the panel and table select representatives from the same fixture.
    const panelSlugs = selectBestVariantPoints(models.map(rigCandidate), { catalogModels: catalog })
      .map((point) => point.modelSlug);
    const tableSlugs = selectLandingBestPerBase(models, context).map((entry) => entry.slug);

    // Then: Qwopus cannot appear in the panel after the table folds it under the same root.
    expect(panelSlugs).toEqual(tableSlugs);
    expect(panelSlugs).toEqual([baseCatalog.slug]);
  });
});

function catalogModel(
  id: string,
  slug: string,
  displayName: string,
  baseModel?: string,
): CatalogModel {
  return {
    id,
    slug,
    display_name: displayName,
    family: "Qwen3.6",
    model_kind: baseModel === undefined ? "base" : "finetune",
    quants: [],
    ...(baseModel === undefined ? {} : { base_model: baseModel }),
  };
}

function model(catalog: CatalogModel, point: number): IndexModel {
  return IndexModelSchema.parse({
    axes: {
      agentic: AXIS_SCORE,
      coding: AXIS_SCORE,
      instruction: AXIS_SCORE,
      knowledge: AXIS_SCORE,
      math: AXIS_SCORE,
      tool_calling: AXIS_SCORE,
    },
    best_run_id: `${catalog.slug}-run`,
    catalog_id: catalog.id,
    composite: { hi: point + 1, lo: point - 1, point },
    composite_full: { hi: point + 1, lo: point - 1, point },
    demo: false,
    est_cost_usd: null,
    family: "Qwen3.6",
    kind: "maintainer_project",
    lane: HEADLINE_LANE,
    model_label: catalog.display_name,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: catalog.slug,
    tier: "standard",
    tokens_to_answer_median: 128,
  });
}

function rigCandidate(entry: IndexModel): RigMatchCandidate {
  return {
    axes: entry.axes,
    demo: false,
    family: entry.family,
    kind: "community",
    lane: HEADLINE_LANE,
    modelLabel: entry.model_label,
    modelSlug: entry.slug,
    nItems: 100,
    nRuns: 1,
    origin: "project_anchor",
    quantLabel: "Q4_K_M",
    ranked: true,
    runId: entry.best_run_id,
    score: entry.composite_full ?? null,
    scoreStatus: "measured",
    tier: "standard",
    tokS: 30,
    trustLabel: "project_anchor",
    vramFootprintGb: 8,
    vramRequiredGb8k: 10,
    latencySMedian: 13.2,
    wallTimeSeconds: 4_200,
  };
}

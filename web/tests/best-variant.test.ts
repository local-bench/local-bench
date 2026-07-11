import { describe, expect, it } from "vitest";
import { selectBestModelVariantPoints, selectBestVariantPoints } from "../lib/best-variant";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import type { RigMatchCandidate } from "../lib/rig-match";
import type { CatalogModel } from "../lib/schemas";

function candidate(overrides: Partial<RigMatchCandidate> = {}): RigMatchCandidate {
  return {
    axes: {},
    demo: false,
    family: "fam",
    kind: "community",
    lane: HEADLINE_LANE,
    modelLabel: "M",
    modelSlug: "m",
    nItems: 100,
    nRuns: 1,
    origin: "project_anchor",
    quantLabel: "Q4_K_M",
    ranked: true,
    runId: "r",
    score: { point: 50, lo: 45, hi: 55 },
    scoreStatus: "measured",
    tier: "standard",
    tokS: 30,
    trustLabel: "project_anchor",
    vramFootprintGb: 8,
    vramRequiredGb8k: 10,
    latencySMedian: 13.2,
    wallTimeSeconds: 4200,
    ...overrides,
  };
}

function catalogModel(overrides: Partial<CatalogModel> = {}): CatalogModel {
  return {
    id: "Fixture/Base",
    slug: "fixture-base",
    display_name: "Fixture Base",
    model_kind: "base",
    quants: [],
    ...overrides,
  };
}

describe("selectBestVariantPoints", () => {
  it("keeps only the best-scoring run per model", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "a", runId: "a-q4", score: { point: 60, lo: 55, hi: 65 }, quantLabel: "Q4_K_M" }),
      candidate({ modelSlug: "a", runId: "a-q8", score: { point: 58, lo: 53, hi: 63 }, quantLabel: "Q8_0" }),
    ]);
    expect(points).toHaveLength(1);
    expect(points[0]?.runId).toBe("a-q4");
  });

  it("excludes demo, anchor, unmeasured, unranked, and quick-tier candidates", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "demo", demo: true }),
      candidate({ modelSlug: "anchor", kind: "anchor" }),
      candidate({ modelSlug: "missing", scoreStatus: "missing", score: null }),
      candidate({ modelSlug: "partial", ranked: false }),
      candidate({ modelSlug: "quick", tier: "quick" }),
      candidate({ modelSlug: "ok", runId: "ok-r" }),
    ]);
    expect(points.map((point) => point.modelSlug)).toEqual(["ok"]);
  });

  it("excludes non-headline lanes (headline is the bounded-final scoped view)", () => {
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "answeronly", lane: "answer-only" }),
      candidate({ modelSlug: "legacycapped", lane: "capped-thinking" }),
      candidate({ modelSlug: "headline", lane: HEADLINE_LANE }),
    ]);
    expect(points.map((point) => point.modelSlug)).toEqual(["headline"]);
  });

  it("marks the efficiency frontier (non-dominated points)", () => {
    // Measured points differentiate on vramFootprintGb (the benchmarked artifact's real
    // size) — catalog vramRequiredGb8k must NOT drive the frontier for measured rows
    // (2026-07-08: mismatched catalog estimates inverted the Qwen/Qwopus dominance).
    const points = selectBestVariantPoints([
      candidate({ modelSlug: "small", runId: "s", score: { point: 40, lo: 35, hi: 45 }, vramFootprintGb: 5, vramRequiredGb8k: 6 }),
      candidate({ modelSlug: "big", runId: "b", score: { point: 70, lo: 65, hi: 75 }, vramFootprintGb: 36, vramRequiredGb8k: 40 }),
      candidate({ modelSlug: "dominated", runId: "d", score: { point: 30, lo: 25, hi: 35 }, vramFootprintGb: 36, vramRequiredGb8k: 40 }),
    ]);
    const frontier = points
      .filter((point) => point.isFrontier)
      .map((point) => point.modelSlug)
      .sort();
    expect(frontier).toEqual(["big", "small"]);
  });

  it("carries per-answer latency onto the best-variant point", () => {
    const points = selectBestVariantPoints([candidate()]);
    expect(points).toHaveLength(1);
    expect(points[0]!.latencySMedian).toBe(13.2);
  });

  it("carries total bench time onto the best-variant point", () => {
    const points = selectBestVariantPoints([candidate()]);
    expect(points).toHaveLength(1);
    expect(points[0]!.wallTimeSeconds).toBe(4200);
  });

  it("collapses a base and fine-tune into one weights-family point", () => {
    const base = catalogModel({
      id: "Qwen/Qwen3.6-27B",
      slug: "qwen3-6-27b",
      display_name: "Qwen3.6 27B",
    });
    const fineTune = catalogModel({
      id: "Jackrong/Qwopus3.6-27B-v2-MTP",
      slug: "qwopus3-6-27b-v2-mtp",
      display_name: "Qwopus3.6 27B v2 MTP",
      model_kind: "finetune",
      base_model: "Qwen/Qwen3.6-27B",
    });

    const points = selectBestVariantPoints(
      [
        candidate({ modelSlug: base.slug, modelLabel: base.display_name, runId: "base", score: { point: 70, lo: 65, hi: 75 } }),
        candidate({
          modelSlug: fineTune.slug,
          modelLabel: fineTune.display_name,
          runId: "fine-tune",
          score: { point: 68, lo: 63, hi: 73 },
        }),
      ],
      { catalogModels: [base, fineTune] },
    );

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      modelSlug: base.slug,
      runId: "base",
      weightsFamilyLabel: "Qwen3.6 27B",
      weightsFamilySlug: base.slug,
    });
  });

  it("lets the fine-tune win the family point when it outscores its base", () => {
    const base = catalogModel({ id: "Base/Model", slug: "base", display_name: "Base Model" });
    const fineTune = catalogModel({
      id: "Tune/Fine",
      slug: "fine",
      display_name: "Fine Tune",
      model_kind: "finetune",
      base_model: base.id,
    });

    const points = selectBestVariantPoints(
      [
        candidate({ modelSlug: base.slug, modelLabel: base.display_name, runId: "base", score: { point: 62, lo: 58, hi: 66 } }),
        candidate({ modelSlug: fineTune.slug, modelLabel: fineTune.display_name, runId: "fine", score: { point: 72, lo: 68, hi: 76 } }),
      ],
      { catalogModels: [base, fineTune] },
    );

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      modelSlug: fineTune.slug,
      modelLabel: "Fine Tune",
      runId: "fine",
      weightsFamilyLabel: "Base Model",
    });
  });

  it("lets the base win the family point when it outscores its fine-tune", () => {
    const base = catalogModel({ id: "Base/Model", slug: "base", display_name: "Base Model" });
    const fineTune = catalogModel({
      id: "Tune/Fine",
      slug: "fine",
      display_name: "Fine Tune",
      model_kind: "finetune",
      base_model: base.id,
    });

    const points = selectBestVariantPoints(
      [
        candidate({ modelSlug: base.slug, modelLabel: base.display_name, runId: "base", score: { point: 73, lo: 69, hi: 77 } }),
        candidate({ modelSlug: fineTune.slug, modelLabel: fineTune.display_name, runId: "fine", score: { point: 70, lo: 66, hi: 74 } }),
      ],
      { catalogModels: [base, fineTune] },
    );

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      modelSlug: base.slug,
      modelLabel: "Base Model",
      runId: "base",
      weightsFamilyLabel: "Base Model",
    });
  });

  it("walks a multi-level fine-tune chain to the root family", () => {
    const root = catalogModel({ id: "Root/Model", slug: "root", display_name: "Root Model" });
    const firstTune = catalogModel({
      id: "Tune/First",
      slug: "first-tune",
      display_name: "First Tune",
      model_kind: "finetune",
      base_model: root.id,
    });
    const secondTune = catalogModel({
      id: "Tune/Second",
      slug: "second-tune",
      display_name: "Second Tune",
      model_kind: "finetune",
      base_model: firstTune.id,
    });

    const points = selectBestVariantPoints(
      [
        candidate({ modelSlug: root.slug, modelLabel: root.display_name, runId: "root", score: { point: 61, lo: 56, hi: 66 } }),
        candidate({
          modelSlug: secondTune.slug,
          modelLabel: secondTune.display_name,
          runId: "second",
          score: { point: 75, lo: 70, hi: 80 },
        }),
      ],
      { catalogModels: [root, firstTune, secondTune] },
    );

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      modelSlug: secondTune.slug,
      runId: "second",
      weightsFamilyLabel: "Root Model",
      weightsFamilySlug: root.slug,
    });
  });

  it("treats an out-of-catalog base_model as its own root", () => {
    const base = catalogModel({ id: "Base/Model", slug: "base", display_name: "Base Model" });
    const externalDerivative = catalogModel({
      id: "Tune/External",
      slug: "external-tune",
      display_name: "External Tune",
      model_kind: "finetune",
      base_model: "Missing/Base",
    });

    const familyPoints = selectBestVariantPoints(
      [
        candidate({ modelSlug: base.slug, modelLabel: base.display_name, runId: "base", score: { point: 62, lo: 58, hi: 66 } }),
        candidate({
          modelSlug: externalDerivative.slug,
          modelLabel: externalDerivative.display_name,
          runId: "external",
          score: { point: 72, lo: 68, hi: 76 },
        }),
      ],
      { catalogModels: [base, externalDerivative] },
    );
    const modelPoints = selectBestModelVariantPoints(
      [
        candidate({ modelSlug: base.slug, modelLabel: base.display_name, runId: "base", score: { point: 62, lo: 58, hi: 66 } }),
        candidate({
          modelSlug: externalDerivative.slug,
          modelLabel: externalDerivative.display_name,
          runId: "external",
          score: { point: 72, lo: 68, hi: 76 },
        }),
      ],
      { catalogModels: [base, externalDerivative] },
    );

    expect(familyPoints.map((point) => point.modelSlug).sort()).toEqual(["base", "external-tune"]);
    expect(familyPoints.find((point) => point.modelSlug === "external-tune")).toMatchObject({
      weightsFamilyLabel: "External Tune",
      weightsFamilySlug: "external-tune",
    });
    expect(modelPoints).toHaveLength(2);
  });
});

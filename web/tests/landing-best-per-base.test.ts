import { describe, expect, it } from "vitest";
import { selectLandingBestPerBase } from "../lib/landing-best-per-base";
import { IndexModelSchema, type IndexModel } from "../lib/schemas";

const AXIS_SCORE = {
  hi: 50,
  lo: 40,
  n: 100,
  n_errors: 0,
  n_no_answer: 0,
  point: 45,
  raw_accuracy: 0.45,
} as const;

describe("landing best-per-base selection", () => {
  it("keeps the base when its fine-tune scores lower", () => {
    const base = model("qwen3-6-27b", "Qwen3.6 27B", 44.4);
    const fineTune = model("qwopus-27b", "Qwopus 27B", 43.3);

    const selected = selectLandingBestPerBase(
      [base, fineTune],
      new Map([[fineTune.slug, base.model_label]]),
    );

    expect(selected.map((row) => row.slug)).toEqual([base.slug]);
  });

  it("keeps the fine-tune when it scores higher than its base", () => {
    const base = model("qwen3-6-27b", "Qwen3.6 27B", 44.4);
    const fineTune = model("qwopus-27b", "Qwopus 27B", 46.1);

    const selected = selectLandingBestPerBase(
      [base, fineTune],
      new Map([[fineTune.slug, base.model_label]]),
    );

    expect(selected.map((row) => row.slug)).toEqual([fineTune.slug]);
  });

  it("keeps same-family models that have different base identities", () => {
    const dense = model("qwen3-6-27b", "Qwen3.6 27B", 44.4);
    const moe = model("qwen3-6-35b-a3b", "Qwen3.6 35B A3B", 45.2);

    const selected = selectLandingBestPerBase([dense, moe], new Map());

    expect(selected.map((row) => row.slug)).toEqual([dense.slug, moe.slug]);
  });
});

function model(slug: string, label: string, point: number): IndexModel {
  return IndexModelSchema.parse({
    axes: {
      agentic: AXIS_SCORE,
      coding: AXIS_SCORE,
      instruction: AXIS_SCORE,
      knowledge: AXIS_SCORE,
      math: AXIS_SCORE,
      tool_calling: AXIS_SCORE,
    },
    best_run_id: `${slug}-run`,
    composite: { hi: point + 1, lo: point - 1, point },
    composite_full: { hi: point + 1, lo: point - 1, point },
    demo: false,
    est_cost_usd: null,
    family: "Qwen3.6",
    kind: "maintainer_project",
    lane: "bounded-final-v2",
    model_label: label,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug,
    tier: "standard",
    tokens_to_answer_median: 128,
  });
}

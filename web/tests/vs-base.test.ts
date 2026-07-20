import { describe, expect, it } from "vitest";
import { buildVsBaseComparison } from "../lib/vs-base";

function score(point: number) {
  return { point, lo: point - 1, hi: point + 1, raw_accuracy: point / 100, n: 10, n_errors: 0, n_no_answer: 0 };
}

describe("buildVsBaseComparison", () => {
  it("computes composite and per-axis deltas from displayed operands where both rows are measured", () => {
    const comparison = buildVsBaseComparison({
      base: {
        catalogId: "Qwen/Qwen3.6-27B",
        displayName: "Qwen3.6 27B",
        slug: "qwen3-6-27b",
        row: {
          bestRunId: "base-run",
          composite: { point: 83.44, lo: 82.44, hi: 84.44 },
          diagnosticComposite: null,
          axes: { knowledge: score(83.44), instruction: score(67), coding: score(20) },
          lane: "bounded-final-v2",
          origin: "project_anchor",
          ranked: true,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
      derivative: {
        catalogId: "Jackrong/Qwopus3.6-27B-v2-MTP",
        displayName: "Qwopus 3.6 27B v2 MTP",
        slug: "qwopus3-6-27b-v2-mtp",
        row: {
          bestRunId: "fine-run",
          composite: { point: 87.36, lo: 86.36, hi: 88.36 },
          diagnosticComposite: null,
          axes: { knowledge: score(87.36), instruction: score(64), tool_calling: score(50) },
          lane: "bounded-final-v2",
          origin: "project_anchor",
          ranked: true,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
    });

    expect(comparison.compositeDelta).toBe(4);
    expect(comparison.missing).toEqual([]);
    expect(comparison.compareHref).toBe("/compare/?left=fine-run&right=base-run");
    expect(comparison.axes.map((axis) => [axis.axis, axis.derivative.point, axis.base.point, axis.delta])).toEqual([
      ["knowledge", 87.36, 83.44, 4],
      ["instruction", 64, 67, -3],
    ]);
  });

  it("reports honest missing states instead of fake deltas", () => {
    const comparison = buildVsBaseComparison({
      base: {
        catalogId: "microsoft/phi-4",
        displayName: "Phi 4",
        slug: "phi-4",
        row: null,
      },
      derivative: {
        catalogId: "microsoft/Phi-4-reasoning",
        displayName: "Phi 4 Reasoning",
        slug: "phi-4-reasoning",
        row: null,
      },
    });

    expect(comparison.compositeDelta).toBeNull();
    expect(comparison.axes).toEqual([]);
    expect(comparison.compareHref).toBe("/compare/?finetune=phi-4-reasoning");
    expect(comparison.missing).toEqual(["base not yet benchmarked", "fine-tune not yet benchmarked"]);
  });

  it("withholds deltas when a side has only previous-index (legacy lane) runs", () => {
    const comparison = buildVsBaseComparison({
      base: {
        catalogId: "google/gemma-4-12b-it",
        displayName: "Gemma 4 12B IT",
        slug: "gemma-4-12b-it",
        row: {
          bestRunId: "base-run",
          composite: { point: 35.2, lo: 33, hi: 38 },
          diagnosticComposite: null,
          axes: { knowledge: score(76) },
          lane: "bounded-final-v2",
          origin: "project_anchor",
          ranked: true,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
      derivative: {
        catalogId: "example/gemma-4-12b-coder",
        displayName: "Gemma 4 12B Coder",
        slug: "gemma-4-12b-coder-fable5",
        row: {
          bestRunId: "legacy-run",
          composite: null,
          diagnosticComposite: { point: 52.9, lo: 51, hi: 54 },
          axes: { knowledge: score(80) },
          lane: "capped-thinking",
          origin: "project_anchor",
          ranked: false,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
    });

    expect(comparison.compositeDelta).toBeNull();
    expect(comparison.axes).toEqual([]);
    expect(comparison.compareHref).toBe("/model/gemma-4-12b-coder-fable5/");
    expect(comparison.missing).toEqual(["fine-tune has only previous-index runs — awaiting a current-index rerun"]);
  });

  it("refuses mixed-season lineage deltas with an explicit bridge state", () => {
    const comparison = buildVsBaseComparison({
      base: {
        catalogId: "base",
        displayName: "Base",
        slug: "base",
        row: {
          axes: { knowledge: score(70) },
          bestRunId: "base-v3",
          composite: { point: 40, lo: 39, hi: 41 },
          diagnosticComposite: null,
          indexVersion: "index-v3.0",
          lane: "bounded-final-v2",
          origin: "project_anchor",
          ranked: true,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
      derivative: {
        catalogId: "tune",
        displayName: "Tune",
        slug: "tune",
        row: {
          axes: { knowledge: score(80) },
          bestRunId: "tune-v4",
          composite: { point: 60, lo: 59, hi: 61 },
          diagnosticComposite: null,
          indexVersion: "index-v4.0",
          lane: "bounded-final-v2",
          origin: "project_anchor",
          ranked: true,
          scoreStatus: "measured",
          trustLabel: "project_anchor",
        },
      },
    });

    expect(comparison.compositeDelta).toBeNull();
    expect(comparison.axes).toEqual([]);
    expect(comparison.missing).toEqual(["different scoring seasons — see bridge"]);
    expect(comparison.compareHref).toBe("/model/tune/#season-bridge");
  });
});

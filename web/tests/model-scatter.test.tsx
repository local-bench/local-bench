import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelScatter } from "../components/model-scatter";
import { ModelVariantBoard } from "../components/model-variant-board";
import { AXIS_KEYS } from "../lib/axis-config";
import type { CommunityBoardRow } from "../lib/community-data";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import type { ModelDataWithConfiguredAxes } from "../lib/data";
import { ModelDataSchema, RunIdSchema, type AxisScore, type ModelRun, type Score } from "../lib/schemas";

const score = { point: 61.2, lo: 59, hi: 63.4 } satisfies Score;
const axisScore = { ...score, raw_accuracy: 0.61, n: 100, n_errors: 0, n_no_answer: 0 } satisfies AxisScore;

function axisScores(): Record<(typeof AXIS_KEYS)[number], AxisScore> {
  return Object.fromEntries(AXIS_KEYS.map((key) => [key, axisScore])) as Record<(typeof AXIS_KEYS)[number], AxisScore>;
}

function runId(value: string): ModelRun["run_id"] {
  return RunIdSchema.parse(value);
}

function run(overrides: Partial<ModelRun> = {}): ModelRun {
  return {
    run_id: runId("model__q4"),
    quant_label: "Q4_K_M",
    vram_footprint_gb: 21.6,
    vram_required_gb_8k: null,
    file_gb: 20.5,
    bpw: 4.8,
    composite: score,
    axes: axisScores(),
    tier: "standard",
    lane: HEADLINE_LANE,
    tokens_to_answer_median: null,
    tok_s: 30,
    est_cost_usd: null,
    hardware: { gpu: null, cpu: null, ram_gb: null, os: null },
    runtime: { name: "llama.cpp", version: "b1", kv_cache_quant: "f16", ctx_len_configured: 32768, parallel_slots: 1 },
    n_items: 100,
    n_errors: 0,
    ranked: true,
    origin: "project_anchor",
    trust_label: "project_anchor",
    wall_time_seconds: 3600,
    score_status: "measured",
    demo: false,
    ...overrides,
  };
}

function model({
  label,
  runs,
  slug,
}: {
  readonly label: string;
  readonly runs: readonly ModelRun[];
  readonly slug: string;
}): ModelDataWithConfiguredAxes {
  return ModelDataSchema.parse({
    slug,
    model_label: label,
    family: "Fixture",
    kind: "community",
    runs,
  }) as ModelDataWithConfiguredAxes;
}

describe("ModelScatter family points", () => {
  it("renders family fine-tunes with distinct markers, a legend, and run links", () => {
    const base = model({ slug: "base", label: "Base Model", runs: [run({ run_id: runId("base__q4") })] });
    const fineTune = model({
      slug: "fine",
      label: "Fine Tune",
      runs: [run({ run_id: runId("fine__q4"), quant_label: "Q4_K_M", vram_footprint_gb: 22.4 })],
    });

    const html = renderToStaticMarkup(
      createElement(ModelScatter, {
        model: base,
        anchorRuns: [],
        familyModels: [{ model: fineTune, relation: "family-finetune" }],
      }),
    );

    expect(html).toContain("This model");
    expect(html).toContain("Family fine-tunes");
    expect(html).toContain('data-point-kind="this-model"');
    expect(html).toContain('data-point-kind="family-finetune"');
    expect(html).toContain('href="/run/fine__q4/"');
    expect(html).toContain("Fine Tune");
  });

  it("renders a fine-tune page's base model points with a separate legend item and run links", () => {
    const fineTune = model({ slug: "fine", label: "Fine Tune", runs: [run({ run_id: runId("fine__q4") })] });
    const base = model({
      slug: "base",
      label: "Base Model",
      runs: [run({ run_id: runId("base__q4"), quant_label: "Q4_K_M", vram_footprint_gb: 20.8 })],
    });

    const html = renderToStaticMarkup(
      createElement(ModelScatter, {
        model: fineTune,
        anchorRuns: [],
        familyModels: [{ model: base, relation: "base-model" }],
      }),
    );

    expect(html).toContain("This model");
    expect(html).toContain("Base model");
    expect(html).toContain('data-point-kind="base-model"');
    expect(html).toContain('href="/run/base__q4/"');
  });

  it("keeps retired-lane family runs off the chart", () => {
    const base = model({ slug: "base", label: "Base Model", runs: [run({ run_id: runId("base__q4") })] });
    const legacyFineTune = model({
      slug: "legacy",
      label: "Legacy Tune",
      runs: [
        run({
          run_id: runId("legacy__q4"),
          lane: "capped-thinking",
          diagnostic_composite: { point: 70, lo: 66, hi: 74 },
        }),
      ],
    });

    const html = renderToStaticMarkup(
      createElement(ModelScatter, {
        model: base,
        anchorRuns: [],
        familyModels: [{ model: legacyFineTune, relation: "family-finetune" }],
      }),
    );

    expect(html).not.toContain('href="/run/legacy__q4/"');
    expect(html).not.toContain("Legacy Tune");
  });

  it("renders a complete community run on the family scatter", () => {
    const adversary = model({
      slug: "community-adversary",
      label: "Community Adversary",
      runs: [run({ origin: "community", trust_label: "community_self_submitted", run_id: runId("community__q4") })],
    });
    const html = renderToStaticMarkup(createElement(ModelScatter, { model: adversary, anchorRuns: [] }));
    expect(html).toContain('href="/run/community__q4/"');
    expect(html).toContain('data-point-kind="this-model"');
  });

  it("hides zero omissions and explains runs that cannot be plotted", () => {
    const complete = model({ slug: "complete", label: "Complete", runs: [run()] });
    const missing = model({
      slug: "missing",
      label: "Missing VRAM",
      runs: [run({ run_id: runId("missing__q4"), vram_footprint_gb: null, vram_required_gb_8k: null })],
    });

    const completeHtml = renderToStaticMarkup(createElement(ModelScatter, { model: complete, anchorRuns: [] }));
    const missingHtml = renderToStaticMarkup(createElement(ModelScatter, { model: missing, anchorRuns: [] }));

    expect(completeHtml).not.toContain("runs lack VRAM data and are not plotted");
    expect(missingHtml).toContain("1 run lacks VRAM data and is not plotted");
  });

  it("plots an env-overlay community row with a distinct linked marker", () => {
    // Given: the server-side community row after the maintainer environment overlay is merged.
    const communityRow = communityFixture({
      hardware: { gpu_name: "RTX 5090", vram_gb: 31.8 },
      maintainerEnvBackfill: { hardware: { vram_gb: true }, perf: { decode_tps: true } },
      perf: { decode_tps: 118.2, tokens_to_answer_median: null, wall_time_seconds: null },
    });

    // When: the model scatter receives that page-level community row set.
    const html = renderToStaticMarkup(createElement(ModelScatter, {
      anchorRuns: [],
      communityRows: [communityRow],
      model: model({ slug: "base", label: "Base Model", runs: [] }),
    }));

    // Then: the row uses the community marker and existing detail/tooltip path.
    expect(html).toContain('data-point-kind="community"');
    expect(html).toContain('href="/model/community-tune/"');
    expect(html).toContain("Community Tune");
    expect(html).toContain("36.7");
    expect(html).toContain("31.8 GB");
    expect(html).toContain("Community runs");

    const boardHtml = renderToStaticMarkup(createElement(ModelVariantBoard, {
      communityRows: [communityRow],
      model: model({ slug: "base", label: "Base Model", runs: [] }),
    }));
    expect(boardHtml).toContain("118.2");
  });

  it("keeps a community row without VRAM on the board but off the scatter", () => {
    // Given: a comparable community result without a plottable memory metric.
    const communityRow = communityFixture({ hardware: { gpu_name: "Unknown GPU", vram_gb: null } });
    const base = model({ slug: "base", label: "Base Model", runs: [run()] });

    // When: both family comparison surfaces receive the exact same source array.
    const boardHtml = renderToStaticMarkup(createElement(ModelVariantBoard, {
      communityRows: [communityRow],
      model: base,
    }));
    const scatterHtml = renderToStaticMarkup(createElement(ModelScatter, {
      anchorRuns: [],
      communityRows: [communityRow],
      model: base,
    }));

    // Then: metric availability affects only the scatter projection.
    expect(boardHtml).toContain("Community Tune");
    expect(boardHtml).toContain('href="/model/community-tune/"');
    expect(scatterHtml).not.toContain('data-point-kind="community"');
    expect(scatterHtml).not.toContain("Community Tune");
    expect(scatterHtml).not.toContain('href="/model/community-tune/"');
  });
});

function communityFixture(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  const measured: NonNullable<CommunityBoardRow["axes"]>[string] = {
    ci: [0.32, 0.42],
    n: 20,
    score: 0.3673,
    status: "measured",
  };
  return {
    artifactSha256: "a".repeat(64),
    axes: {
      coding: measured,
      instruction: measured,
      knowledge: measured,
      math: measured,
      tool_use: measured,
    },
    compositeFull: 0.3673,
    detailPath: "/model/community-tune/",
    displayName: "Community Tune",
    family: "Fixture",
    globalRank: 1,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    origin: "community",
    partialComposite: 0.3673,
    quantLabel: "Q2_K",
    ranked: true,
    submissionId: "ticket_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ...overrides,
  };
}

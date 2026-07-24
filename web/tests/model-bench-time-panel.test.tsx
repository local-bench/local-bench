import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelBenchTimePanel } from "../components/model-bench-time-panel";
import type { CommunityBoardRow } from "../lib/community-data";
import type { ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "../lib/data";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import { ModelSlugSchema, RunIdSchema, type AxisScore, type Score } from "../lib/schemas";

const PAGE_ARTIFACT_SHA = "a".repeat(64);
const LIVE_ARTIFACT_SHA = "b".repeat(64);
const score = { point: 61.2, lo: 59, hi: 63.4 } satisfies Score;
const axisScore = {
  ...score,
  raw_accuracy: 0.61,
  n: 100,
  n_errors: 0,
  n_no_answer: 0,
} satisfies AxisScore;

type ConfiguredRun = ModelDataWithConfiguredAxes["runs"][number];

function run(overrides: Partial<ConfiguredRun> = {}): ConfiguredRun {
  return {
    run_id: RunIdSchema.parse("qwen__q4"),
    quant_label: "Q4_K_M",
    vram_footprint_gb: 21.6,
    vram_required_gb_8k: null,
    file_gb: 20.5,
    bpw: 4.8,
    composite: score,
    axes: {
      agentic: axisScore,
      knowledge: axisScore,
      instruction: axisScore,
      tool_calling: axisScore,
      coding: axisScore,
      math: axisScore,
    },
    tier: "standard",
    lane: HEADLINE_LANE,
    tokens_to_answer_median: null,
    tok_s: 30,
    est_cost_usd: null,
    hardware: { gpu: null, cpu: null, ram_gb: null, os: null },
    runtime: {
      name: "llama.cpp",
      version: "b1",
      kv_cache_quant: "f16",
      ctx_len_configured: 32768,
      parallel_slots: 1,
    },
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
  artifacts = [],
  label,
  runs,
  slug,
}: {
  readonly artifacts?: ModelDataWithConfiguredAxes["artifacts"];
  readonly label: string;
  readonly runs: readonly ConfiguredRun[];
  readonly slug: string;
}): ModelDataWithConfiguredAxes {
  return {
    artifacts,
    demo: false,
    family: "Qwen",
    kind: "community",
    model_kind: "base",
    model_label: label,
    runs: [...runs],
    slug: ModelSlugSchema.parse(slug),
  };
}

function liveRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: LIVE_ARTIFACT_SHA,
    compositeFull: 0.515,
    detailPath: "/model/bonsai-27b-ternary/",
    displayName: "bonsai-27b-ternary-q2-0",
    family: "Qwen",
    globalRank: null,
    hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    origin: "community",
    partialComposite: null,
    perf: { decode_tps: 118, tokens_to_answer_median: 900, wall_time_seconds: 1800 },
    quantLabel: "Q2_0",
    submissionId: "ticket_live",
    ...overrides,
  };
}

function fixtures(): {
  readonly communityRows: readonly CommunityBoardRow[];
  readonly familyModels: readonly ModelFamilyScatterModel[];
  readonly model: ModelDataWithConfiguredAxes;
} {
  const pageModel = model({
    artifacts: [{ file_sha256: PAGE_ARTIFACT_SHA, quant_label: "Q4_K_M" }],
    label: "Qwen3.6 27B",
    runs: [run({ wall_time_seconds: 3600 })],
    slug: "qwen3-6-27b",
  });
  const qwopus = model({
    label: "Qwopus 3.6 27B v2 MTP",
    runs: [run({
      composite: { point: 58.4, lo: 56, hi: 60 },
      quant_label: "Q3_K_M",
      run_id: RunIdSchema.parse("qwopus__q3"),
      wall_time_seconds: 2700,
    })],
    slug: "qwopus-v2",
  });
  const bonsai = model({
    artifacts: [{ file_sha256: LIVE_ARTIFACT_SHA, quant_label: "Q2_0" }],
    label: "Bonsai 27B Ternary",
    runs: [],
    slug: "bonsai-27b-ternary",
  });
  return {
    communityRows: [liveRow()],
    familyModels: [
      { model: qwopus, relation: "family-finetune" },
      { model: bonsai, relation: "family-finetune" },
    ],
    model: pageModel,
  };
}

function render(overrides: Partial<ReturnType<typeof fixtures>> = {}): string {
  return renderToStaticMarkup(createElement(ModelBenchTimePanel, { ...fixtures(), ...overrides }));
}

describe("ModelBenchTimePanel", () => {
  it("orders every eligible row by ascending wall time", () => {
    const html = render();
    const positions = ["Bonsai Ternary · Q2_0", "Qwopus v2 MTP · Q3_K_M", "Q4_K_M"]
      .map((label) => html.indexOf(label));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect([...positions].sort((left, right) => left - right)).toEqual(positions);
  });

  it("renders own, family, and live rows with contextual labels, scores, hardware, and links", () => {
    const html = render();
    expect(html).toContain(">Q4_K_M<");
    expect(html).toContain("Qwopus v2 MTP · Q3_K_M");
    expect(html).toContain("Bonsai Ternary · Q2_0");
    expect(html).not.toContain("declared as");
    expect(html).toContain("61.20");
    expect(html).toContain("58.40");
    expect(html).toContain("51.50");
    expect(html).toContain("RTX 5090 · 32 GB");
    expect(html).toContain('href="/run/qwen__q4/"');
    expect(html).toContain('href="/model/bonsai-27b-ternary/"');
  });

  it("excludes legacy capped-thinking-lane runs", () => {
    const base = fixtures();
    const legacy = run({
      lane: "capped-thinking",
      quant_label: "LEGACY_Q8",
      run_id: RunIdSchema.parse("qwen__legacy"),
      wall_time_seconds: 300,
    });
    const html = render({ model: { ...base.model, runs: [...base.model.runs, legacy] } });
    expect(html).not.toContain("LEGACY_Q8");
    expect(html).not.toContain("/run/qwen__legacy/");
  });

  it("renders nothing when fewer than two eligible timed rows exist", () => {
    const base = fixtures();
    expect(render({
      communityRows: [],
      familyModels: [],
      model: base.model,
    })).toBe("");
  });

  it("marks only the shortest run with run-oriented flame copy", () => {
    const html = render();
    expect(html.split("\u{1F525}").length - 1).toBe(1);
    expect(html).toContain("Shortest full-suite run this season");
    expect(html).not.toContain("fastest model");
  });

  it("places the first row tooltip below its focus target", () => {
    const html = render();
    expect(html).toContain("top-[calc(100%-4px)]");
  });

  it("keeps both misread guards in visible copy", () => {
    const html = render();
    expect(html).toContain("Elapsed time for this exact full-suite run; not a general model-speed measurement.");
    expect(html).toContain("this is not an inference-speed ranking.");
  });
});

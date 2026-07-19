import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomeLeaderboard, sortLeaderboardRows } from "../components/home-leaderboard";
import { IndexModelSchema, ModelSlugSchema, RunIdSchema, type IndexModel } from "../lib/schemas";

const AXIS_SCORE = {
  hi: 90,
  lo: 80,
  n: 96,
  n_errors: 0,
  n_no_answer: 0,
  point: 85,
  raw_accuracy: 0.85,
} as const;
const FULL_AXES = {
  agentic: AXIS_SCORE,
  coding: AXIS_SCORE,
  instruction: AXIS_SCORE,
  knowledge: AXIS_SCORE,
  math: AXIS_SCORE,
  tool_calling: AXIS_SCORE,
};

describe("home leaderboard runtime column", () => {
  it("renders runtime name plus version and a dash when absent", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          model("llama", "Llama Row", { name: "llama.cpp", version: "b1234" }),
          model("missing", "Missing Runtime", undefined),
        ],
      }),
    );

    expect(html).toContain("Runtime");
    expect(html).not.toContain("Tool-call format");
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
    expect(html).toContain("Missing Runtime");
    expect(html).toContain("—");
  });

  it("sorts rows by runtime label", () => {
    const sorted = sortLeaderboardRows(
      [
        model("vllm", "VLLM Row", { name: "vllm", version: "0.24.0" }),
        model("llama", "Llama Row", { name: "llama.cpp", version: "b1234" }),
      ],
      { key: "runtime", direction: "asc" },
    );

    expect(sorted.map((row) => row.slug)).toEqual(["llama", "vllm"]);
  });
});

describe("home leaderboard provenance labels", () => {
  it("preserves optional board-row provenance fields in the index schema", () => {
    const parsed = IndexModelSchema.parse({
      ...rawModel("gemma", "Gemma Anchor", undefined),
      agentic_provenance: "project_attested",
      origin: "project_anchor",
      submitter_display_name: "Quant Cowboy",
      trust_label: "project_anchor",
    });
    const legacy = IndexModelSchema.parse(rawModel("legacy", "Legacy Row", undefined));

    expect(parsed).toMatchObject({
      agentic_provenance: "project_attested",
      origin: "project_anchor",
      submitter_display_name: "Quant Cowboy",
      trust_label: "project_anchor",
    });
    expect(legacy).not.toHaveProperty("origin");
    expect(legacy).not.toHaveProperty("agentic_provenance");
  });

  it("renders the single project-run badge for project-owned rows", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("gemma", "Gemma Ranked", undefined),
            agentic_provenance: "project_attested",
            origin: "project_anchor",
            trust_label: "project_anchor",
          }),
        ],
      }),
    );

    expect(html).toContain("Run by");
    expect(html.match(/project run/giu)).toHaveLength(1);
    expect(html).not.toContain("attested");
  });

  it("renders community agentic provenance and submitter display names as plain text", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("community", "Community Row", undefined),
            agentic_provenance: "self_reported",
            origin: "community",
            submitter_display_name: "Quant Cowboy",
            trust_label: "community_re_scored",
          }),
        ],
      }),
    );

    expect(html).toContain("submitted as Quant Cowboy — unverified");
    expect(html).not.toContain("self-reported");
  });

  it("keeps incomplete catalog shells off the ranked board", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("shell", "Catalog Shell", undefined),
            composite: null,
            ranked: false,
            score_status: "missing",
          }),
        ],
      }),
    );

    expect(html).not.toContain("Catalog Shell");
    expect(html).toContain("0 complete ranked runs");
  });

  it("sorts static-composite mode by composite_static instead of composite_full", () => {
    const sorted = sortLeaderboardRows(
      [
        IndexModelSchema.parse({
          ...rawModel("full-high", "Full High", undefined),
          composite: { hi: 95, lo: 85, point: 90 },
          composite_static: { hi: 18, lo: 12, point: 15 },
          static_index_version: "static-suite-v2",
        }),
        IndexModelSchema.parse({
          ...rawModel("static-high", "Static High", undefined),
          composite: { hi: 25, lo: 15, point: 20 },
          composite_static: { hi: 83, lo: 77, point: 80 },
          static_index_version: "static-suite-v2",
        }),
      ],
      { key: "composite", direction: "desc" },
      { scoreMode: "static" },
    );

    expect(sorted.map((row) => row.slug)).toEqual(["static-high", "full-high"]);
  });

  // 2026-07-11 deep-dive decision: the headline board now SURFACES the Static Index as a
  // clearly-labelled secondary column (the agentic axis is near-floor for current entrants,
  // so composite_static discriminates better). It must read as secondary, never as the rank.
  it("renders the Static Index as a labelled secondary column on the headline board", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("static-track", "Static Track", undefined),
            composite_full: { hi: 45, lo: 35, point: 40 },
            composite_static: { hi: 65, lo: 55, point: 60 },
            lane: "bounded-final-v2",
            static_index_version: "static-suite-v2",
          }),
        ],
      }),
    );

    expect(html).toContain("static-suite-v2");
    expect(html).toContain("secondary track");
    expect(html).toContain("Local Intelligence Index");
  });

  it("omits the Static Index column in static score mode where it would duplicate the rank", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        scoreMode: "static",
        models: [
          IndexModelSchema.parse({
            ...rawModel("static-track", "Static Track", undefined),
            composite_full: { hi: 45, lo: 35, point: 40 },
            composite_static: { hi: 65, lo: 55, point: 60 },
            lane: "bounded-final-v2",
            static_index_version: "static-suite-v2",
          }),
        ],
      }),
    );

    expect(html).not.toContain("static-suite-v2 · secondary track");
  });

  it("renders a fine-tune chip when the lineage map covers a row", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("finetune-row", "Finetune Row", undefined),
            lane: "bounded-final-v2",
          }),
        ],
        fineTuneBaseBySlug: new Map([["finetune-row", "Base Model 27B"]]),
      }),
    );

    expect(html).toContain("Fine-tune of");
    expect(html).toContain("Base Model 27B");
  });
});

function model(
  slug: string,
  label: string,
  runtime: IndexModel["runtime"],
): IndexModel {
  const row = IndexModelSchema.parse(rawModel(slug, label, runtime));
  return row;
}

function rawModel(
  slug: string,
  label: string,
  runtime: IndexModel["runtime"],
): Record<string, unknown> {
  const row = {
    axes: FULL_AXES,
    best_run_id: RunIdSchema.parse(`${slug}-run`),
    composite: { hi: 90, lo: 80, point: 85 },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "community",
    lane: "bounded-final-v2",
    model_label: label,
    n_runs: 1,
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: ModelSlugSchema.parse(slug),
    submitted_by: null,
    tier: "standard",
    tokens_to_answer_median: 128,
  };
  if (runtime === undefined) return row;
  return runtime.name === "vllm" ? { ...row, runtime, serving_provenance: vllmProvenance() } : { ...row, runtime };
}

function vllmProvenance(): Record<string, unknown> {
  return {
    runtime: "vllm",
    engine_version: "0.24.0",
    engine_executable_sha256: "f".repeat(64),
    dependency_lock_sha256: "a".repeat(64),
    runtime_identity_sha256: "b".repeat(64),
    snapshot: {
      repo: "org/model",
      revision: "c".repeat(40),
      merkle_sha256: "d".repeat(64),
      files: [{ path: "model.safetensors", sha256: "e".repeat(64), size_bytes: 1 }],
    },
    determinism: {
      engine_log_evidence: ["verified"],
      engine_log_semantic_verdict: true,
      two_start_canary_passed: true,
    },
    numerics: {
      dtype: "bfloat16",
      kv_cache_quant: "bfloat16",
      mamba_ssm_cache_dtype: null,
      model_config_mamba_ssm_dtype: null,
      quantization: "compressed-tensors",
    },
  };
}

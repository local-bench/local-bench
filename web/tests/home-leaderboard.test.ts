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
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b1234");
    expect(html).toContain("Missing Runtime");
    expect(html).toContain("—");
  });

  it("sorts rows by runtime label", () => {
    const sorted = sortLeaderboardRows(
      [
        model("vllm", "VLLM Row", { name: "vLLM", version: "0.9.0" }),
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

  it("renders trust and attested chips for project-anchor five-axis rows", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("gemma", "Gemma Anchor", undefined),
            agentic_provenance: "project_attested",
            axes: { agentic: AXIS_SCORE },
            origin: "project_anchor",
            trust_label: "project_anchor",
          }),
        ],
      }),
    );

    expect(html).toContain("project anchor");
    expect(html).toContain("attested");
    expect(html).not.toContain("community-reported");
    expect(html).toContain('href="/methodology"');
  });

  it("renders community agentic provenance and submitter display names as plain text", () => {
    const html = renderToStaticMarkup(
      createElement(HomeLeaderboard, {
        models: [
          IndexModelSchema.parse({
            ...rawModel("community", "Community Row", undefined),
            agentic_provenance: "self_reported",
            axes: { agentic: AXIS_SCORE },
            origin: "community",
            submitter_display_name: "Quant Cowboy",
            trust_label: "community_re_scored",
          }),
        ],
      }),
    );

    expect(html).toContain("community");
    expect(html).toContain("self-reported");
    expect(html).toContain("submitted by Quant Cowboy");
    expect(html).not.toMatch(/<a[^>]*>submitted by Quant Cowboy<\/a>/);
  });

  it("sorts static-composite mode by composite_static instead of composite_full", () => {
    const sorted = sortLeaderboardRows(
      [
        IndexModelSchema.parse({
          ...rawModel("full-high", "Full High", undefined),
          composite: { hi: 95, lo: 85, point: 90 },
          composite_static: { hi: 18, lo: 12, point: 15 },
          static_index_version: "static-suite-v1",
        }),
        IndexModelSchema.parse({
          ...rawModel("static-high", "Static High", undefined),
          composite: { hi: 25, lo: 15, point: 20 },
          composite_static: { hi: 83, lo: 77, point: 80 },
          static_index_version: "static-suite-v1",
        }),
      ],
      { key: "composite", direction: "desc" },
      { scoreMode: "static" },
    );

    expect(sorted.map((row) => row.slug)).toEqual(["static-high", "full-high"]);
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
    axes: {},
    best_run_id: RunIdSchema.parse(`${slug}-run`),
    composite: { hi: 90, lo: 80, point: 85 },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "community",
    lane: "capped-thinking",
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
  return runtime === undefined ? row : { ...row, runtime };
}

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomeLeaderboard, sortLeaderboardRows } from "../components/home-leaderboard";
import { ModelSlugSchema, RunIdSchema, type IndexModel } from "../lib/schemas";

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

function model(
  slug: string,
  label: string,
  runtime: IndexModel["runtime"],
): IndexModel {
  const row: IndexModel = {
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

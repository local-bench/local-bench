import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomeLeaderboard } from "../components/home-leaderboard";
import {
  ARCHIVED_OPERATING_POINT_LABEL,
  BOARD_DEFAULT_OPERATING_POINT_VIEW,
} from "../lib/operating-point-view";
import { IndexModelSchema, type IndexModel } from "../lib/schemas";

const NOTICE = "Operating point changed from 8k static reasoning to 32k. Cross-profile scores are not compute-matched.";
const ROW_8K = operatingPointModel("fixture-8k", "Fixture 8k", 50, { id: "generic_think_tags_8192_v1" });
const ROW_32K = operatingPointModel("fixture-32k", "Fixture 32k", 60, currentExecutionProfile());

describe("operating-point board view", () => {
  it("ships the mixed board as the one-line default-view configuration", () => {
    expect(BOARD_DEFAULT_OPERATING_POINT_VIEW).toBe("mixed");
  });

  it("renders both configured default states and keeps archived rows on a stable deep link", () => {
    // Given: one complete ranked row from each preserved operating point.
    const models = [ROW_8K, ROW_32K];

    // When: the shipping default, later 32k default, and its archived URL render.
    const mixedHtml = renderBoard(models, "mixed", null);
    const deeperDefaultHtml = renderBoard(models, "32k-default", null);
    const archivedHtml = renderBoard(models, "32k-default", "archived-8k");

    // Then: mixed shows both, the later default collapses 8k, and the URL restores it.
    expect(mixedHtml).toContain("Fixture 8k");
    expect(mixedHtml).toContain("Fixture 32k");
    expect(mixedHtml).toContain(NOTICE);
    expect(deeperDefaultHtml).not.toContain("Fixture 8k");
    expect(deeperDefaultHtml).toContain("Fixture 32k");
    expect(deeperDefaultHtml).not.toContain(NOTICE);
    expect(archivedHtml).toContain("Fixture 8k");
    expect(archivedHtml).not.toContain("Fixture 32k");
    expect(archivedHtml).toContain(NOTICE);
    expect(archivedHtml).toContain('href="/model/fixture-8k/"');
    expect(archivedHtml).toContain(`href="?operating-point=archived-8k"`);
    expect(archivedHtml).toContain(ARCHIVED_OPERATING_POINT_LABEL);
  });

  it("uses only 8k and 32k cohort copy throughout the operating-point UI", () => {
    const html = renderBoard([ROW_8K, ROW_32K], "mixed", null);

    expect(html).toMatch(/>8k<|>32k</u);
    expect(html).not.toMatch(/\b(?:Current|Legacy)\b/u);
  });
});

function renderBoard(
  models: readonly IndexModel[],
  defaultOperatingPointView: "mixed" | "32k-default",
  operatingPointQuery: string | null,
): string {
  return renderToStaticMarkup(
    <HomeLeaderboard
      defaultOperatingPointView={defaultOperatingPointView}
      defaultShowAllVariants
      indexVersion="index-v4.2"
      models={models}
      operatingPointQuery={operatingPointQuery}
    />,
  );
}

function operatingPointModel(
  slug: string,
  modelLabel: string,
  score: number,
  executionProfile: { readonly id: string } | ReturnType<typeof currentExecutionProfile>,
): IndexModel {
  return IndexModelSchema.parse({
    axes: {
      agentic: axisScore(score, 96),
      coding: axisScore(score, 141),
      instruction: axisScore(score, 294),
      knowledge: axisScore(score, 400),
      math: axisScore(score, 139),
      tool_use: axisScore(score, 96),
    },
    best_run_id: `${slug}-run`,
    composite: { hi: score + 0.01, lo: score - 0.01, point: score },
    composite_full: { hi: score + 0.01, lo: score - 0.01, point: score },
    demo: false,
    est_cost_usd: null,
    execution_profile: executionProfile,
    family: "Fixture",
    gpu: null,
    index_version: "index-v4.2",
    kind: "maintainer_project",
    lane: "bounded-final-v2",
    model_label: modelLabel,
    n_runs: 1,
    origin: "project_anchor",
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug,
    tier: "standard",
    tokens_to_answer_median: 128,
    trust_label: "project_anchor",
  });
}

function axisScore(point: number, n: number) {
  return {
    hi: point + 0.01,
    lo: point - 0.01,
    n,
    n_errors: 0,
    n_no_answer: 0,
    point,
    raw_accuracy: point / 100,
  };
}

function currentExecutionProfile() {
  return {
    agentic_context_tokens: 32768,
    agentic_max_generated_tokens_per_task: 65536,
    agentic_max_output_tokens_per_turn: 1024,
    agentic_max_turns: 40,
    answer_stops: ["</think>"],
    chat_template_kwargs: { enable_thinking: true },
    context_extension_policy: "none",
    context_fit_policy: "exact-or-fail",
    id: "generic_think_tags_32768_v1",
    kv_cache_k_dtype: "f16",
    kv_cache_v_dtype: "f16",
    per_task_timeout_s: 3000,
    prompt_renderer_engine: "llama.cpp.apply-template",
    runtime_probe_passed: true,
    schema_version: "localbench.execution_profile.v2",
    selection_policy_id: "gguf-effective-template-v1",
    selection_reason: "gguf_generic_think_confirmed",
    semantic_sha256: "e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058",
    server_context_tokens: 65536,
    static_final_tokens: 16384,
    static_max_generated_tokens: 49152,
    static_think_tokens: 32768,
    template_sha256: "f".repeat(64),
    template_source: "gguf-default",
  } as const;
}

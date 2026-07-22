import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComparePicker } from "../components/compare-picker";
import { getCompareConfigs } from "../lib/compare";
import type { CommunityBoardRow } from "../lib/community-data";
import { getIndexData, getModelData } from "../lib/data";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import { ModelDataSchema } from "../lib/schemas";

const CURRENT_RUN_ID = "gemma-4-12b-it__gemma-4-12b-it-qat-ud-q4kxl-s2v5";
const LEGACY_RUN_ID = "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q4";

describe("compare configs", () => {
  it("includes measured configs with nonstandard quant labels and labels index coverage", async () => {
    // Given measured site data that includes a project-anchor Unsloth dynamic quant.
    const index = await getIndexData();
    const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));

    // When compare configs are built from measured runs.
    const configs = getCompareConfigs(models);

    // Then the nonstandard QAT Q4_K_XL measured variant is available and marked rank-comparable.
    expect(
      configs.find((config) => config.modelSlug === "gemma-4-12b-it" && config.quantLabel === "QAT Q4_K_XL"),
    ).toMatchObject({
      coverage: "full",
      modelSlug: "gemma-4-12b-it",
      quantLabel: "QAT Q4_K_XL",
    });
    expect(configs.find((config) => config.modelSlug === "gemma-4-12b-it" && config.quantLabel === "Q8_0")).toBeUndefined();
  });

  it("defaults to current-lane configs and quarantines legacy runs behind diagnostics", async () => {
    // Given measured site data with one current ranked run and previous-index diagnostics.
    const configs = await realCompareConfigs();

    // When the picker renders without URL-selected run ids.
    const html = renderToStaticMarkup(
      createElement(ComparePicker, {
        configs,
        fineTunePresets: [],
        initialLeftId: null,
        initialRightId: null,
      }),
    );

    // Then selected cards are current-index only; legacy rows without explicit trust are excluded.
    expect(configs.some((config) => config.runId === LEGACY_RUN_ID)).toBe(false);
    expect(html).toContain(CURRENT_RUN_ID);
    expect(html).not.toContain(`value="${LEGACY_RUN_ID}"`);
    expect(html).not.toContain("62.3");
    expect(html).not.toContain("62.0");
  });

  it("does not render an Index delta when a URL-selected side is a legacy run", async () => {
    // Given a legacy run id selected through the same prop path used for URL ids.
    const configs = await realCompareConfigs();

    // When the compare picker renders that diagnostic side.
    const html = renderToStaticMarkup(
      createElement(ComparePicker, {
        configs,
        fineTunePresets: [],
        initialLeftId: LEGACY_RUN_ID,
        initialRightId: CURRENT_RUN_ID,
      }),
    );

    // Then an untrusted legacy URL id cannot enter the comparison population.
    expect(html).not.toContain("Diagnostic score (retired lane)");
    expect(html).not.toContain(LEGACY_RUN_ID);
    expect(html).toContain("Local Intelligence Index delta");
  });

  it("uses diagnostic_composite for retired-lane configs when standard composite is null", () => {
    // Given a current run and an opt-in retired-lane diagnostic whose standard composite is null.
    const configs = getCompareConfigs([
      ModelDataSchema.parse({
        demo: false,
        family: "Fixture",
        kind: "community",
        model_kind: "base",
        model_label: "Fixture Model",
        runs: [
          modelRunFixture({
            composite: { point: 35.2, lo: 32.8, hi: 37.9 },
            lane: HEADLINE_LANE,
            quantLabel: "Q4_K_M",
            runId: "fixture-current-run",
          }),
          modelRunFixture({
            composite: null,
            diagnosticComposite: { point: 62.3, lo: 60.0, hi: 64.0 },
            lane: "capped-thinking",
            quantLabel: "Q8_0",
            runId: "fixture-legacy-run",
          }),
        ],
        slug: "fixture-model",
      }),
    ]);

    // When the selected side is the retired-lane diagnostic.
    const html = renderToStaticMarkup(
      createElement(ComparePicker, {
        configs,
        fineTunePresets: [],
        initialLeftId: "fixture-legacy-run",
        initialRightId: "fixture-current-run",
      }),
    );

    // Then the diagnostic is available only under the previous-index framing.
    expect(configs.find((config) => config.runId === "fixture-legacy-run")).toMatchObject({
      composite: { point: 62.3, lo: 60.0, hi: 64.0 },
      scoreScope: "previous-index",
    });
    expect(html).toContain("Previous-index diagnostics");
    expect(html).toContain("Diagnostic score (retired lane)");
    expect(html).toContain("62.3");
    expect(html).not.toContain("Local Intelligence Index delta");
  });

  it("joins live configs to catalog artifact VRAM and display identity", () => {
    const artifactSha256 = "a".repeat(64);
    const catalogModel = ModelDataSchema.parse({
      artifacts: [{
        file_gb: 7.2,
        file_sha256: artifactSha256,
        quant_label: "Q2_0",
        vram_gb_8k: 9.5,
      }],
      demo: false,
      family: "Qwen3.6",
      kind: "community",
      model_label: "Bonsai 27B Ternary",
      runs: [],
      slug: "bonsai-27b-ternary",
    });
    const liveRow: CommunityBoardRow = {
      artifactSha256,
      axes: {},
      compositeFull: 0.3673,
      detailPath: "/model/bonsai-27b-ternary/",
      displayName: "bonsai-27b-ternary",
      family: "qwen35",
      globalRank: 1,
      headlineComplete: true,
      identityLabel: "community-declared, identity-unverified",
      lineage: undefined,
      indexVersion: "index-v4.2",
      measuredHeadlineWeight: 1,
      missingHeadlineWeight: 0,
      origin: "community",
      partialComposite: 0.3673,
      quantLabel: "Q2_0",
      ranked: false,
      submissionId: "ticket_bonsai_compare",
    };

    const config = getCompareConfigs([catalogModel], [liveRow])
      .find((candidate) => candidate.id === liveRow.submissionId);

    expect(config).toMatchObject({
      fitTierGb: 12,
      modelLabel: "Bonsai 27B Ternary",
      vramEstimate: { effectiveRequiredGb: 9.5, weightsGb: 7.2 },
    });
  });
});

async function realCompareConfigs() {
  const index = await getIndexData();
  const models = await Promise.all(index.models.map((model) => getModelData(model.slug)));
  return getCompareConfigs(models);
}

function modelRunFixture({
  composite,
  diagnosticComposite,
  lane,
  quantLabel,
  runId,
}: {
  readonly composite: { readonly point: number; readonly lo: number; readonly hi: number } | null;
  readonly diagnosticComposite?: { readonly point: number; readonly lo: number; readonly hi: number };
  readonly lane: string;
  readonly quantLabel: string;
  readonly runId: string;
}) {
  return {
    axes: {},
    composite,
    diagnostic_composite: diagnosticComposite,
    demo: false,
    est_cost_usd: null,
    file_gb: null,
    hardware: { cpu: null, gpu: null, os: null, ram_gb: null },
    lane,
    n_errors: 0,
    n_items: 10,
    origin: "project_anchor",
    quant_label: quantLabel,
    ranked: lane === HEADLINE_LANE,
    run_id: runId,
    runtime: {
      ctx_len_configured: 8192,
      kv_cache_quant: "q8_0",
      name: "llama.cpp",
      parallel_slots: 1,
      version: "b1234",
    },
    score_status: "measured",
    tier: "standard",
    tok_s: 20,
    tokens_to_answer_median: 128,
    trust_label: "project_anchor",
    vram_footprint_gb: 12,
  };
}

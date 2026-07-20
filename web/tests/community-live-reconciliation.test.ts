import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityLeaderboardRow } from "../components/community-leaderboard-row";
import { adaptLegacyBoardRow } from "../lib/board-adapter";
import { parseCommunityLiveBoard, reconcileCommunityRows, type LiveBoardRow } from "../lib/community-live";
import type { CommunityBoardRow } from "../lib/community-data";
import { buildFamilyResolutionContext } from "../lib/family-resolution";
import type { CatalogModel } from "../lib/schemas";

const GROUP_ID = `community-group:${"1".repeat(32)}`;
const LIVE_ONLY_GROUP_ID = `community-group:${"2".repeat(32)}`;
const SUBMISSION_ID = `ticket_${"3".repeat(32)}`;

function liveRow(overrides: Partial<LiveBoardRow> = {}): LiveBoardRow {
  return {
    axes: {
      coding: { ci: [0.4, 0.6], n: 20, score: 0.5, status: "measured" },
    },
    community_model_group_id: GROUP_ID,
    conformance: {},
    coverage_profile_id: "full-exec-6axis-v1",
    group_path: `community/groups/${"1".repeat(32)}.json`,
    headline_complete: true,
    index_version: "index-v4.1",
    lineage: { base_model: ["Qwen/Qwen3.5-9B"] },
    model: {
      declared_name: "Declared model",
      display_name: "Live model",
      family: "Qwen3.5",
      file_sha256: "a".repeat(64),
      identity_status: "unverified",
      model_system_key: `artifact:${"a".repeat(64)}`,
      quant_label: "Q4_K_M",
    },
    origin: "community",
    receipt_references: { coding_receipt_sha256: null },
    rescore_modes: { mmlu_pro: "rescored" },
    scorecard_id: "scorecard-v6",
    scores: {
      composite_full: 0.5,
      composite_static: 0.55,
      headline_score: 0.5,
      known_headline_contribution: 0.5,
      measured_headline_weight: 1,
      missing_headline_weight: 0,
      partial_composite: 0.5,
      partial_composite_scope: "measured_headline_axes",
      rank_scope: "full-exec-6axis-v1",
      static_index_version: "static-suite-v3",
    },
    submission_id: SUBMISSION_ID,
    submitter: { display_name: "Ada", github_login: "octocat", key_fingerprint: "abcdef123456" },
    suite_release_id: "suite-v2-full-exec-tooluse-5axis-v2",
    timestamps: {
      published_at: "2026-07-18T04:00:00Z",
      submitted_at: "2026-07-18T03:00:00Z",
      validated_at: "2026-07-18T03:30:00Z",
    },
    trust: {
      agentic_provenance: "self_reported",
      coding_state: "pending",
      replicated: false,
      tier: "re-scored",
      trust_label: "community_re_scored",
      verification_level: "bundle_rescored",
    },
    ...overrides,
  };
}

function envelope(rows: readonly unknown[]) {
  return {
    board_digest: "f".repeat(64),
    edge_block_revision: 2,
    generated_at: "2026-07-18T04:00:10Z",
    omitted_rows: 0,
    publication_revision: 7,
    rows,
    schema_version: "localbench.community_live_board.v1",
  };
}

const bakedLineage = {
  artifact_sha256: "a".repeat(64),
  association: {
    artifact_to_repo: "unverified" as const,
    basis: "maintainer-associated" as const,
    note: "Maintainer reviewed association.",
  },
  card_declared_edges: [{
    base: "Qwen/Qwen3.5-9B",
    base_revision: "b".repeat(40),
    child: "owner/model",
    child_revision: "c".repeat(40),
    source: "hf-model-card" as const,
  }],
  repo: { id: "owner/model", revision: "c".repeat(40) },
  resolution: { resolved_at: "2026-07-18T01:30:00Z", status: "complete" as const },
};

function bakedRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: "a".repeat(64),
    axes: {},
    communityModelGroupId: GROUP_ID,
    declaredBaseModels: [],
    compositeFull: 0.4,
    detailPath: "/model/qwen3-5-9b",
    displayName: "Baked model",
    family: "Qwen3.5",
    globalRank: null,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.1",
    lineage: bakedLineage,
    measuredHeadlineWeight: 0.75,
    missingHeadlineWeight: 0.25,
    partialComposite: 0.4,
    quantLabel: "Q5_K_M",
    ranked: false,
    submissionId: SUBMISSION_ID,
    submitterDisplayName: null,
    submitterGithubLogin: null,
    submitterKeyFingerprint: null,
    timestamps: null,
    trust: null,
    ...overrides,
  };
}

describe("community live reconciliation", () => {
  it("resolves a resubmitted Bonsai row without a baked submission-id match", () => {
    // Given: the live row is a new submission carrying only Bonsai's catalog artifact SHA.
    const root = catalogModel({
      id: "Qwen/Qwen3.6-27B",
      slug: "qwen3-6-27b",
      display_name: "Qwen3.6 27B",
      family: "Qwen3.6",
    });
    const bonsai = catalogModel({
      id: "prism-ml/Ternary-Bonsai-27B-unpacked",
      slug: "bonsai-27b-ternary",
      display_name: "Bonsai 27B Ternary",
      family: "Qwen3.6",
      base_model: root.id,
      model_kind: "finetune",
      quants: [{
        label: "Q2_0",
        file_sha256: "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757",
      }],
    });
    const context = buildFamilyResolutionContext([root, bonsai], [], new Map());

    // When: reconciliation receives no baked row with the new submission ID.
    const [merged] = reconcileCommunityRows([], [liveRow({
      lineage: { base_model: [] },
      model: {
        ...liveRow().model,
        family: "qwen35",
        file_sha256: "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757",
        model_system_key: "artifact:868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757",
      },
    })], context);

    // Then: resolver fields and the artifact owner's model page are attached independently of submission ID.
    expect(merged).toMatchObject({
      catalogFamily: "Qwen3.6",
      chainCatalogIds: [bonsai.id, root.id],
      confidence: "artifact-sha",
      detailPath: "/model/bonsai-27b-ternary",
      rootCatalogId: root.id,
      rootSlug: root.slug,
    });
  });

  it("uses live scoring fields while preserving maintainer-reviewed baked lineage", () => {
    const [merged] = reconcileCommunityRows([bakedRow()], [liveRow()]);

    expect(merged).toMatchObject({
      axes: { coding: { score: 0.5, status: "measured" } },
      displayName: "Live model",
      lineage: bakedLineage,
      partialComposite: 0.5,
      submitterDisplayName: "Ada",
      submitterGithubLogin: "octocat",
      trust: { trust_label: "community_re_scored" },
    });
  });

  it("preserves parsed environment telemetry through reconciliation and rendered cells", () => {
    const parsed = parseCommunityLiveBoard(envelope([liveRow({
      hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
      perf: {
        decode_tps: 71.5,
        latency_s_median: 13.4,
        tokens_to_answer_median: 512,
        wall_time_seconds: 3660,
      },
      runtime: { backend: "cuda", name: "llama.cpp", version: "b7421" },
    })]));
    if (parsed === null) throw new Error("expected parsed live board");

    const [merged] = reconcileCommunityRows([bakedRow()], parsed.rows);
    if (merged === undefined) throw new Error("expected reconciled community row");
    const html = renderToStaticMarkup(createElement(
      "table",
      null,
      createElement("tbody", null, createElement(CommunityLeaderboardRow, {
        axisKeys: [],
        rank: 1,
        row: merged,
        showAgenticColumn: false,
        showStaticIndexColumn: false,
      })),
    ));

    expect(merged).toMatchObject({
      hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
      perf: {
        decode_tps: 71.5,
        latency_s_median: 13.4,
        tokens_to_answer_median: 512,
        wall_time_seconds: 3660,
      },
      runtime: { backend: "cuda", name: "llama.cpp", version: "b7421" },
    });
    expect(html).toContain("llama.cpp");
    expect(html).toContain("RTX 5090 · 32 GB");
    expect(html).toContain("512");
    expect(html).toContain("~13 s");
    expect(html).toContain("1 h");
  });

  it("preserves the catalog family through a successful live refresh", () => {
    const [merged] = reconcileCommunityRows(
      [bakedRow({ catalogFamily: "Qwen3.6", family: "qwen35" })],
      [liveRow({ model: { ...liveRow().model, family: "qwen35" } })],
    );

    expect(merged).toMatchObject({ catalogFamily: "Qwen3.6", family: "qwen35" });
  });

  it("appends a live-only row without a detail link for an unbaked group", () => {
    const groupSuffix = "2".repeat(32);
    const [merged] = reconcileCommunityRows([], [liveRow({
      community_model_group_id: LIVE_ONLY_GROUP_ID,
      group_path: `community/groups/${groupSuffix}.json`,
    })]);

    expect(merged).toMatchObject({ detailPath: null, displayName: "Live model" });
  });

  it("includes a live-published project-anchor row before the next static bake", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({
      badge: "project-run",
      origin: "project_anchor",
      trust: undefined,
    })]);

    expect(merged).toMatchObject({ displayName: "Live model", submissionId: SUBMISSION_ID });
  });

  it("keeps live lineage enrichment when no baked row exists", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({ lineage_enrichment: bakedLineage })]);

    expect(merged?.lineage).toEqual(bakedLineage);
  });

  it("uses all six axes when estimating legacy partial measured weight", () => {
    const measured = { ci: null, n: 1, score: 0.5, status: "measured" as const };
    const missing = { ci: null, n: 0, score: null, status: "not_measured" as const };
    const legacy = adaptLegacyBoardRow(liveRow({
      axes: {
        agentic: measured,
        coding: measured,
        instruction_following: measured,
        knowledge: missing,
        math: missing,
        tool_calling: missing,
      },
      headline_complete: false,
      scores: { ...liveRow().scores, composite_full: null, headline_score: null },
    }));
    const [merged] = reconcileCommunityRows([], [{
      ...legacy,
      measuredHeadlineWeight: null,
      missingHeadlineWeight: null,
    }]);

    expect(merged?.measuredHeadlineWeight).toBe(0.5);
  });

  it("normalizes a near-consistent coverage pair to one displayed whole", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({
      scores: {
        ...liveRow().scores,
        measured_headline_weight: 0.53,
        missing_headline_weight: 0.48,
      },
    })]);

    expect(merged).toMatchObject({
      coverageConsistent: true,
      measuredHeadlineWeight: 0.53,
      missingHeadlineWeight: 0.47,
    });
    expect(((merged?.measuredHeadlineWeight ?? 0) + (merged?.missingHeadlineWeight ?? 0)) * 100).toBe(100);
  });

  it("keeps a materially inconsistent coverage pair and marks it", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({
      scores: {
        ...liveRow().scores,
        measured_headline_weight: 0.53,
        missing_headline_weight: 0.44,
      },
    })]);

    expect(merged).toMatchObject({
      coverageConsistent: false,
      measuredHeadlineWeight: 0.53,
      missingHeadlineWeight: 0.44,
    });
  });

  it("treats the exact coverage tolerance boundary as consistent", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({
      scores: {
        ...liveRow().scores,
        measured_headline_weight: 0.53,
        missing_headline_weight: 0.45,
      },
    })]);

    expect(merged).toMatchObject({
      coverageConsistent: true,
      measuredHeadlineWeight: 0.53,
      missingHeadlineWeight: 0.47,
    });
  });

  it("drops a baked row absent after a successful live fetch", () => {
    expect(reconcileCommunityRows([bakedRow()], [])).toEqual([]);
  });

  it("never restores the removed community route from a baked row", () => {
    const [merged] = reconcileCommunityRows([bakedRow({ detailPath: `/community/model/${"1".repeat(32)}` })], [liveRow()]);
    expect(merged?.detailPath).toBeNull();
  });
});

function catalogModel(overrides: Partial<CatalogModel>): CatalogModel {
  return {
    id: "Fixture/Model",
    slug: "fixture-model",
    display_name: "Fixture Model",
    model_kind: "base",
    quants: [],
    ...overrides,
  };
}

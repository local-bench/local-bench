import { describe, expect, it } from "vitest";
import { reconcileCommunityRows, type LiveBoardRow } from "../lib/community-live";
import type { CommunityBoardRow } from "../lib/community-data";

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

  it("appends a live-only row without a detail link for an unbaked group", () => {
    const groupSuffix = "2".repeat(32);
    const [merged] = reconcileCommunityRows([], [liveRow({
      community_model_group_id: LIVE_ONLY_GROUP_ID,
      group_path: `community/groups/${groupSuffix}.json`,
    })]);

    expect(merged).toMatchObject({ detailPath: null, displayName: "Live model" });
  });

  it("keeps live lineage enrichment when no baked row exists", () => {
    const [merged] = reconcileCommunityRows([], [liveRow({ lineage_enrichment: bakedLineage })]);

    expect(merged?.lineage).toEqual(bakedLineage);
  });

  it("uses all six axes when estimating legacy partial measured weight", () => {
    const measured = { ci: null, n: 1, score: 0.5, status: "measured" as const };
    const missing = { ci: null, n: 0, score: null, status: "not_measured" as const };
    const [merged] = reconcileCommunityRows([], [liveRow({
      axes: {
        agentic: measured,
        coding: measured,
        instruction_following: measured,
        knowledge: missing,
        math: missing,
        tool_calling: missing,
      },
      headline_complete: false,
      scores: { composite_full: null },
    })]);

    expect(merged?.measuredHeadlineWeight).toBe(0.5);
  });

  it("drops a baked row absent after a successful live fetch", () => {
    expect(reconcileCommunityRows([bakedRow()], [])).toEqual([]);
  });

  it("never restores the removed community route from a baked row", () => {
    const [merged] = reconcileCommunityRows([bakedRow({ detailPath: `/community/model/${"1".repeat(32)}` })], [liveRow()]);
    expect(merged?.detailPath).toBeNull();
  });
});

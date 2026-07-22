import type { LiveBoardRow } from "../../lib/community-live";

export const BONSAI_ARTIFACT_SHA = "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757";

export function bonsaiLiveEnvelope(): unknown {
  const measured = (score: number): LiveBoardRow["axes"][string] => ({
    ci: [score - 0.02, score + 0.02],
    n: 20,
    score,
    status: "measured",
  });
  const row = {
    axes: {
      agentic: measured(0.42),
      coding: measured(0.85),
      instruction_following: measured(0.63),
      knowledge: measured(0.51),
      math: measured(0.9),
      tool_calling: measured(0.74),
    },
    community_model_group_id: "community-group:efe0634c6e494e06a349aedbff372cbf",
    conformance: {},
    coverage_profile_id: "full-exec-6axis-v1",
    group_path: "community/groups/efe0634c6e494e06a349aedbff372cbf.json",
    headline_complete: true,
    index_version: "index-v4.2",
    lineage: { base_model: [] },
    model: {
      declared_name: "bonsai-27b-ternary",
      display_name: "bonsai-27b-ternary",
      family: "qwen35",
      file_sha256: BONSAI_ARTIFACT_SHA,
      identity_status: "unverified",
      model_system_key: `artifact:${BONSAI_ARTIFACT_SHA}`,
      quant_label: "Q2_0",
    },
    origin: "community",
    receipt_references: { coding_receipt_sha256: null },
    rescore_modes: { mmlu_pro: "rescored" },
    scorecard_id: "scorecard-v6",
    scores: {
      composite_full: 0.3673,
      composite_static: 0.469,
      headline_score: 0.3673,
      known_headline_contribution: 0.3673,
      measured_headline_weight: 1,
      missing_headline_weight: 0,
      partial_composite: 0.3673,
      partial_composite_scope: "measured_headline_axes",
      rank_scope: "full-exec-6axis-v1",
      static_index_version: "static-suite-v3",
    },
    submission_id: "ticket_cc352811a58d4022b3044eb28abce178",
    submitter: { display_name: null, github_login: null, key_fingerprint: null },
    suite_release_id: "suite-v2-full-exec-tooluse-5axis-v2",
    timestamps: {
      published_at: "2026-07-18T04:00:00Z",
      submitted_at: "2026-07-18T03:00:00Z",
      validated_at: "2026-07-18T03:30:00Z",
    },
    trust: {
      agentic_provenance: "self_reported",
      coding_state: "measured",
      replicated: false,
      tier: "re-scored",
      trust_label: "community_re_scored",
      verification_level: "bundle_rescored",
    },
  } satisfies LiveBoardRow;

  return {
    board_digest: "f".repeat(64),
    edge_block_revision: 2,
    generated_at: "2026-07-18T04:00:10Z",
    omitted_rows: 0,
    publication_revision: 7,
    rows: [row],
    schema_version: "localbench.community_live_board.v1",
  };
}

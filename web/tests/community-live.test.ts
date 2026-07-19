import { describe, expect, it } from "vitest";
import {
  parseCommunityLiveBoard,
  type LiveBoardRow,
} from "../lib/community-live";
import { axisLabel } from "../lib/axis-config";

const GROUP_ID = `community-group:${"1".repeat(32)}`;
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

describe("community live board boundary", () => {
  it("accepts the complete strict contract", () => {
    const parsed = parseCommunityLiveBoard(envelope([liveRow()]));

    expect(parsed).toMatchObject({ droppedRows: 0, rows: [{ submissionId: SUBMISSION_ID }] });
  });

  it("drops one poisoned row without blanking valid rows", () => {
    const poisoned = { ...liveRow(), model: { ...liveRow().model, display_name: "x".repeat(121) } };
    const parsed = parseCommunityLiveBoard(envelope([liveRow(), poisoned, liveRow({ submission_id: `ticket_${"4".repeat(32)}` })]));

    expect(parsed?.rows).toHaveLength(2);
    expect(parsed?.droppedRows).toBe(1);
  });

  it.each([
    ["bidi family", () => ({ ...liveRow(), model: { ...liveRow().model, family: "Qwen\u202e" } })],
    ["seventeen axes", () => ({
      ...liveRow(),
      axes: Object.fromEntries(Array.from({ length: 17 }, (_, index) => [`axis-${index}`, { ci: null, n: 1, score: 0.5, status: "measured" }])),
    })],
    ["bad fingerprint", () => ({
      ...liveRow(),
      submitter: { display_name: "Ada", github_login: "octocat", key_fingerprint: "not-hex" },
    })],
    ["bidi github login", () => ({
      ...liveRow(),
      submitter: { display_name: "Ada", github_login: "octo\u202e", key_fingerprint: "abcdef123456" },
    })],
  ])("drops a row containing %s", (_name, makeRow) => {
    const parsed = parseCommunityLiveBoard(envelope([makeRow()]));

    expect(parsed).toMatchObject({ droppedRows: 1, rows: [] });
  });

  it("tolerates additive envelope fields", () => {
    expect(parseCommunityLiveBoard({ ...envelope([liveRow()]), unexpected: true })).toMatchObject({ droppedRows: 0 });
  });

  it("adapts the final submitter handle and server-owned project badge", () => {
    const parsed = parseCommunityLiveBoard(envelope([{
      ...liveRow({ origin: "project_anchor" }),
      badge: "project-run",
      submitter: { github_login: null, key_fingerprint: null, unverified_handle: "Ada Runner" },
    }]));

    expect(parsed?.rows[0]).toMatchObject({
      badge: "project-run",
      submitterDisplayName: "Ada Runner",
    });
  });

  it("adapts optional runtime, hardware, and performance telemetry when valid", () => {
    const parsed = parseCommunityLiveBoard(envelope([{
      ...liveRow(),
      hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
      perf: { decode_tps: 71.5, tokens_to_answer_median: 512, wall_time_seconds: 3660 },
      runtime: { backend: "cuda", name: "llama.cpp", version: "b7421" },
    }]));

    expect(parsed?.rows[0]).toMatchObject({
      hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
      perf: { decode_tps: 71.5, tokens_to_answer_median: 512, wall_time_seconds: 3660 },
      runtime: { backend: "cuda", name: "llama.cpp", version: "b7421" },
    });
  });

  it("keeps rows with absent or malformed optional telemetry and drops each malformed field", () => {
    const parsed = parseCommunityLiveBoard(envelope([
      liveRow(),
      {
        ...liveRow({ submission_id: `ticket_${"5".repeat(32)}` }),
        hardware: { gpu_name: "RTX 5090", vram_gb: -1 },
        perf: { decode_tps: Number.POSITIVE_INFINITY, tokens_to_answer_median: 12, wall_time_seconds: 4 },
        runtime: { backend: null, name: "x".repeat(301), version: null },
      },
    ]));

    expect(parsed).toMatchObject({ droppedRows: 0 });
    expect(parsed?.rows).toHaveLength(2);
    expect(parsed?.rows[0]).not.toHaveProperty("runtime");
    expect(parsed?.rows[0]).not.toHaveProperty("hardware");
    expect(parsed?.rows[0]).not.toHaveProperty("perf");
    expect(parsed?.rows[1]).not.toHaveProperty("runtime");
    expect(parsed?.rows[1]).not.toHaveProperty("hardware");
    expect(parsed?.rows[1]).not.toHaveProperty("perf");
  });

  it("normalizes legacy live axis keys without overriding canonical values", () => {
    const parsed = parseCommunityLiveBoard(envelope([liveRow({
      axes: {
        agentic: { ci: null, n: 1, score: 0.8, status: "measured" },
        call_formatting: { ci: null, n: 1, score: 0.6, status: "measured" },
        tool_use: { ci: null, n: 1, score: 0.4, status: "measured" },
      },
    })]));

    expect(parsed?.rows[0]?.axes).toMatchObject({
      agentic: { score: 0.8 },
      tool_calling: { score: 0.6 },
    });
    expect(parsed?.rows[0]?.axes).not.toHaveProperty("tool_use");
    expect(parsed?.rows[0]?.axes).not.toHaveProperty("call_formatting");
    expect(axisLabel("instruction_following")).toBe("Instruction following");
  });
});

import { describe, expect, it } from "vitest";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { canonicalJson, sha256Hex } from "../functions/_lib/submission-canonical";
import { projectionKey } from "../functions/_lib/submission-storage";
import { rebuildCommunityLiveBoard } from "../functions/_lib/community-live-board";
import { LiveBoardRowSchema, parseBoardEnvelope } from "../lib/board-adapter";
import {
  MIGRATION_0002,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0006,
  MIGRATION_0008,
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  MIGRATION_0012,
  MIGRATION_0013,
  MIGRATION_0014,
  MIGRATION_0015,
  MIGRATION_0017,
  RAW_BUNDLE_SHA,
  createEnv,
  statusUpdate,
} from "./submission-test-support";

const COMMUNITY_GROUP_ID = "community-group:7d5b421c43554896a63b453ca57c43d3";
const SUBMISSION_ID = "ticket_75e2314e2a81417fb11b6396d3ebea35";

describe("live-board-function <-> board-adapter schema consistency", () => {
  it("parses a realistic stored projection with zero dropped rows", async () => {
    const env = await schemaEnv();
    await insertStoredProjection(env, "octocat");

    const payload = await rebuildCommunityLiveBoard(env);
    const parsed = parseBoardEnvelope(payload);

    expect(parsed).toMatchObject({ droppedRows: 0 });
    expect(parsed?.rows).toHaveLength(1);
    const row = LiveBoardRowSchema.parse(payload.rows[0]);
    expect(row.provenance_notes).toEqual([
      "index_relabeled_from:index-v3.0",
      "attestation_missing:appworld_c (96 items)",
    ]);
    expect(row.runtime?.build_flags).toBe(
      "version: 1 (38c66ad); built with MSVC 19.44.35228.0 for Windows AMD64",
    );
  });

  it("counts a row rejected by the client schema as omitted", async () => {
    const env = await schemaEnv();
    await insertStoredProjection(env, "invalid_login");

    const payload = await rebuildCommunityLiveBoard(env);

    expect(payload.rows).toEqual([]);
    expect(payload.omitted_rows).toBe(1);
  });
});

function schemaEnv() {
  return createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
      MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012, MIGRATION_0013,
      MIGRATION_0014, MIGRATION_0015, MIGRATION_0017,
    ],
  });
}

async function insertStoredProjection(
  env: Awaited<ReturnType<typeof schemaEnv>>,
  githubLogin: string,
): Promise<void> {
  const base = AcceptedResultProjectionV2Schema.parse(
    statusUpdate("accepted", RAW_BUNDLE_SHA, "community")["projection"],
  );
  const projection = AcceptedResultProjectionV2Schema.parse({
    ...base,
    model: {
      ...base.model,
      display_name: "qwen3-5-9b-q4-k-m",
      file_sha256: "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
      model_system_key: "artifact:03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
    },
    provenance_notes: [
      "index_relabeled_from:index-v3.0",
      ...Array.from(
        { length: 96 },
        (_, index) => `attestation_missing:appworld_c/${index.toString(16).padStart(64, "0")}_${index}`,
      ),
    ],
    runtime: {
      build_flags: "version: 1 (38c66ad)\nbuilt with MSVC 19.44.35228.0 for Windows AMD64",
      name: "llama.cpp",
      version: "b9852",
    },
  });
  const objectSha = await sha256Hex(canonicalJson(projection));
  await env.SUBMISSIONS.put(projectionKey(objectSha), canonicalJson(projection));
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, submitter_display_name, github_login, status, raw_bundle_sha256,
      idempotency_key, publish_state, published_at, validated_at, suite_release_id,
      suite_manifest_sha256, projection_sha256, projection_object_sha256, projection_r2_key,
      community_model_group_id, state_revision, zt1_decision, zt1_coding_state
    ) values (?, 'community', ?, 'Fixture Submitter', ?, 'accepted', ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, 1, 'publishable', 'self_reported_exec')`,
  ).bind(
    SUBMISSION_ID, `public_key:${"d".repeat(64)}`, githubLogin, RAW_BUNDLE_SHA, RAW_BUNDLE_SHA,
    "2026-07-18 01:00:00", "2026-07-18 00:00:00", projection.suite_release_id,
    projection.suite_manifest_sha256, projection.artifact_hashes.projection_sha256, objectSha,
    projectionKey(objectSha), COMMUNITY_GROUP_ID,
  ).run();
}

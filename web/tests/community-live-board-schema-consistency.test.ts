import { describe, expect, it } from "vitest";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { canonicalJson, sha256Hex } from "../functions/_lib/submission-canonical";
import { projectionKey } from "../functions/_lib/submission-storage";
import { rebuildCommunityLiveBoard, relabeledIndexVersion } from "../functions/_lib/community-live-board";
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
  completeProjection,
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
    expect(row.execution_profile).toMatchObject({
      id: "generic_think_tags_8192_v1",
      runtime_probe_passed: true,
      selection_policy_id: "gguf-effective-template-v1",
    });
    expect(row.provenance_notes).toEqual([
      "index_relabeled_from:index-v3.0",
      "attestation_missing:appworld_c (96 items)",
      "execution_profile:generic_think_tags_8192_v1",
    ]);
    expect(row.runtime?.build_flags).toBe(
      "version: 1 (38c66ad); built with MSVC 19.44.35228.0 for Windows AMD64",
    );
  });

  it("publishes an unmapped GGUF bounded-final row for moderation without ranking it", async () => {
    // Given: an otherwise valid llama.cpp projection from an older client with no structured profile.
    const env = await schemaEnv();
    await insertStoredProjection(env, "octocat", {
      executionProfile: "absent",
      complete: true,
      submissionId: "ticket_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    });

    // When: the server materializes the public board.
    const payload = await rebuildCommunityLiveBoard(env);
    const row = LiveBoardRowSchema.parse(payload.rows[0]);

    // Then: publication succeeds, but ranking is held for moderation.
    expect(row.ranked).toBe(false);
    expect(row.moderation_queue_marker).toBe("legacy_execution_profile_review");
    expect(row.execution_profile).toBeUndefined();
  });

  it("holds an unmapped profile-less row WITHOUT hf identity for moderation (the pre-0.4.12 gguf-repo-only shape)", async () => {
    // Given: the exact row class B6 exists for - an older client's --gguf-repo-only
    // submission: complete, llama.cpp, no structured profile, and NO hf identity.
    const env = await schemaEnv();
    await insertStoredProjection(env, "octocat", {
      complete: true,
      executionProfile: "absent",
      hfIdentity: "absent",
      submissionId: "ticket_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    });

    // When: the server materializes the public board.
    const payload = await rebuildCommunityLiveBoard(env);
    const row = LiveBoardRowSchema.parse(payload.rows[0]);

    // Then: absence of hf identity must NOT exempt the row from the admission gate.
    expect(row.ranked).toBe(false);
    expect(row.moderation_queue_marker).toBe("legacy_execution_profile_review");
    expect(row.execution_profile).toBeUndefined();
  });

  it("keeps the archived 44.62 base row ranked with its maintained profile mapping", async () => {
    // Given: the archived base submission predates the structured projection field.
    const env = await schemaEnv();
    await insertStoredProjection(env, "octocat", {
      complete: true,
      executionProfile: "absent",
      submissionId: "ticket_783cba6e5d2e42a786823884da1fcd15",
    });

    // When: the server materializes the legacy project anchor.
    const payload = await rebuildCommunityLiveBoard(env);
    const row = LiveBoardRowSchema.parse(payload.rows[0]);

    // Then: the archived bundle mapping supplies a comparable public profile.
    expect(row.ranked).toBe(true);
    expect(row.execution_profile).toEqual({ id: "generic_think_tags_8192_v1" });
    expect(row.provenance_notes?.filter((note) => note.startsWith("execution_profile:")))
      .toEqual(["execution_profile:generic_think_tags_8192_v1"]);
  });

  it("links the corrected 0.4.13 fusion rerun as superseding the suppressed 0.4.11 row", async () => {
    // Given: the corrected rerun's projection (structured profile, probe-verified).
    const env = await schemaEnv();
    await insertStoredProjection(env, "octocat", {
      complete: true,
      submissionId: "ticket_cbeac7e27cc34d5da8053557423d5aff",
    });

    // When: the server materializes the public board.
    const payload = await rebuildCommunityLiveBoard(env);
    const row = LiveBoardRowSchema.parse(payload.rows[0]);

    // Then: the row ranks normally and carries the corrective supersedes link.
    expect(row.ranked).toBe(true);
    expect(row.supersedes_submission_id).toBe("ticket_4dec3df918b34f9bb74bcc98e6766a17");
    expect(row.execution_profile).toMatchObject({ id: "generic_think_tags_8192_v1" });
  });

  it("counts a row rejected by the client schema as omitted", async () => {
    const env = await schemaEnv();
    await insertStoredProjection(env, "invalid_login");

    const payload = await rebuildCommunityLiveBoard(env);

    expect(payload.rows).toEqual([]);
    expect(payload.omitted_rows).toBe(1);
  });
});

describe("maintainer index-version relabels", () => {
  it("relabels the bonsai submission from v4.1 to v4.2 with a provenance note", () => {
    const result = relabeledIndexVersion("ticket_cc352811a58d4022b3044eb28abce178", "index-v4.1");
    expect(result.value).toBe("index-v4.2");
    expect(result.note).toBe("index_version_relabeled:index-v4.1->index-v4.2:maintainer:2026-07-22");
  });

  it("never fires for an unmapped submission or a mismatched stored label", () => {
    expect(relabeledIndexVersion("ticket_75e2314e2a81417fb11b6396d3ebea35", "index-v4.1"))
      .toEqual({ note: null, value: "index-v4.1" });
    expect(relabeledIndexVersion("ticket_cc352811a58d4022b3044eb28abce178", "index-v4.2"))
      .toEqual({ note: null, value: "index-v4.2" });
    expect(relabeledIndexVersion("ticket_cc352811a58d4022b3044eb28abce178", null))
      .toEqual({ note: null, value: null });
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
  fixture: {
    readonly complete?: boolean;
    readonly executionProfile?: "absent" | "present";
    readonly hfIdentity?: "absent" | "present";
    readonly submissionId?: string;
  } = {},
): Promise<void> {
  const base = AcceptedResultProjectionV2Schema.parse(
    fixture.complete === true
      ? completeProjection(RAW_BUNDLE_SHA, "community")
      : statusUpdate("accepted", RAW_BUNDLE_SHA, "community")["projection"],
  );
  const projection = AcceptedResultProjectionV2Schema.parse({
    ...base,
    ...(fixture.executionProfile === "absent" ? {} : {
      execution_profile: {
        answer_stops: ["</think>"],
        chat_template_kwargs: { enable_thinking: true },
        id: "generic_think_tags_8192_v1",
        prompt_renderer_engine: "llama.cpp.apply-template",
        runtime_probe_passed: true,
        selection_policy_id: "gguf-effective-template-v1",
        selection_reason: "gguf_template_thinking_markers",
        template_sha256: "f".repeat(64),
        template_source: "gguf-default",
      },
    }),
    model: {
      ...base.model,
      display_name: "qwen3-5-9b-q4-k-m",
      file_sha256: "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
      ...(fixture.hfIdentity === "absent" ? {} : {
        hf: {
          filename: "Qwen3.5-9B-Q4_K_M.gguf",
          repo: "Qwen/Qwen3.5-9B-GGUF",
          revision: "a".repeat(40),
        },
      }),
      model_system_key: "artifact:03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
    },
    provenance_notes: [
      "index_relabeled_from:index-v3.0",
      "execution_profile:client-forged",
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
    fixture.submissionId ?? SUBMISSION_ID,
    `public_key:${"d".repeat(64)}`, githubLogin, RAW_BUNDLE_SHA, RAW_BUNDLE_SHA,
    "2026-07-18 01:00:00", "2026-07-18 00:00:00", projection.suite_release_id,
    projection.suite_manifest_sha256, projection.artifact_hashes.projection_sha256, objectSha,
    projectionKey(objectSha), COMMUNITY_GROUP_ID,
  ).run();
}

import { afterEach, describe, expect, it } from "vitest";
import { AcceptedResultProjectionV2Schema } from "../functions/_lib/submission-contracts";
import { canonicalJson, sha256Hex } from "../functions/_lib/submission-canonical";
import { projectionKey } from "../functions/_lib/submission-storage";
import { rebuildCommunityLiveBoard } from "../functions/_lib/community-live-board";
import { onRequestGet as getCommunityBoard } from "../functions/api/board/community.json";
import { onRequestPost as forceBoardRebuild } from "../functions/api/admin/board/rebuild";
import { onRequestPost as suppressSubmission } from "../functions/api/admin/submissions/[submissionId]/suppress";
import { onRequestPost as migratePublishThenModerate } from "../functions/api/admin/migrate-publish-then-moderate";
import {
  ADMIN_SECRET,
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
  SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID,
  TEST_COMMUNITY_GROUP_ID,
  createEnv,
  getRequest,
  jsonRequest,
  statusUpdate,
} from "./submission-test-support";

const originalCaches = Object.getOwnPropertyDescriptor(globalThis, "caches");

afterEach(() => {
  if (originalCaches === undefined) {
    Reflect.deleteProperty(globalThis, "caches");
  } else {
    Object.defineProperty(globalThis, "caches", originalCaches);
  }
});

describe("materialized community live board", () => {
  it("builds the bounded public contract and omits missing projections", async () => {
    const env = await boardEnv();
    await insertBoardFixture(env, {
      githubLogin: "fixture-user",
      submissionId: "ticket_fixture_board_a",
      publishedAt: "2026-07-18 01:00:00",
    });
    await insertBoardFixture(env, {
      projectionMissing: true,
      rawSha: "b".repeat(64),
      submissionId: "ticket_fixture_board_missing",
      publishedAt: "2026-07-18 02:00:00",
    });

    const payload = await rebuildCommunityLiveBoard(env);
    const stored = await env.SUBMISSIONS.get("board/community-live.json");
    expect(stored).not.toBeNull();
    expect(payload).toMatchObject({
      omitted_rows: 1,
      schema_version: "localbench.community_live_board.v1",
    });
    expect(payload.rows).toHaveLength(1);
    expect(payload.rows[0]).toMatchObject({
      community_model_group_id: TEST_COMMUNITY_GROUP_ID,
      group_path: `community/groups/${"1".repeat(32)}.json`,
      origin: "community",
      submission_id: "ticket_fixture_board_a",
      submitter: { github_login: "fixture-user" },
    });
    expect(JSON.stringify(payload)).not.toMatch(/r2_key|zt1_|capability|admin|upload_/i);
    expect(payload.board_digest).toMatch(/^[0-9a-f]{64}$/);
  });

  it("serves the R2 object through one bare-path cache key and rejects query parameters", async () => {
    const env = await boardEnv();
    await insertBoardFixture(env, { submissionId: "ticket_fixture_cache", publishedAt: "2026-07-18 01:00:00" });
    await rebuildCommunityLiveBoard(env);
    const memory = new Map<string, Response>();
    Object.defineProperty(globalThis, "caches", {
      configurable: true,
      value: {
        default: {
          match: async (request: Request) => memory.get(request.url)?.clone(),
          put: async (request: Request, response: Response) => { memory.set(request.url, response.clone()); },
        },
      },
    });

    const first = await getCommunityBoard({ env, request: getRequest("/api/board/community.json") });
    await env.SUBMISSIONS.put("board/community-live.json", JSON.stringify({ changed: true }));
    const second = await getCommunityBoard({ env, request: getRequest("/api/board/community.json") });
    const queried = await getCommunityBoard({ env, request: getRequest("/api/board/community.json?cache=bust") });

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(await second.json()).toEqual(await first.json());
    expect(queried.status).toBe(400);
    expect([...memory.keys()]).toEqual(["https://local-bench.ai/api/board/community.json"]);
  });

  it("allows only the admin credential to force a board rebuild", async () => {
    const base = await boardEnv();
    const env = { ...base, VALIDATOR_API_SECRET: "fixture-validator-secret" };
    const refused = await forceBoardRebuild({
      env,
      request: jsonRequest("/api/admin/board/rebuild", {}, {
        "x-localbench-validator-secret": "fixture-validator-secret",
      }),
    });
    const rebuilt = await forceBoardRebuild({
      env,
      request: jsonRequest("/api/admin/board/rebuild", {}, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });
    expect(refused.status).toBe(401);
    expect(rebuilt.status).toBe(200);
    expect(await rebuilt.json()).toMatchObject({ schema_version: "localbench.community_live_board.v1" });
  });

  it("rebuilds the materialized object immediately after suppression", async () => {
    const env = await boardEnv();
    await insertBoardFixture(env, { submissionId: "ticket_fixture_suppress", publishedAt: "2026-07-18 01:00:00" });
    await rebuildCommunityLiveBoard(env);
    const response = await suppressSubmission({
      env,
      params: { submissionId: "ticket_fixture_suppress" },
      request: jsonRequest("/api/admin/submissions/ticket_fixture_suppress/suppress", {
        reason: "synthetic fixture moderation",
      }, { "x-localbench-admin-secret": ADMIN_SECRET }),
    });
    const stored = await env.SUBMISSIONS.get("board/community-live.json");
    const payload = stored === null ? null : await new Response(stored.body).json();
    expect(response.status).toBe(200);
    expect(payload).toMatchObject({ rows: [] });
  });

  it("migrates publishable preview rows exactly once and rebuilds the board", async () => {
    const env = await boardEnv();
    await insertBoardFixture(env, { submissionId: "ticket_fixture_migration", publishedAt: "2026-07-18 01:00:00" });
    await env.DB.prepare(
      "update submissions set publish_state = 'preview', published_at = null where submission_id = 'ticket_fixture_migration'",
    ).run();
    const request = () => jsonRequest("/api/admin/migrate-publish-then-moderate", {}, {
      "x-localbench-admin-secret": ADMIN_SECRET,
    });
    const first = await migratePublishThenModerate({ env, request: request() });
    const second = await migratePublishThenModerate({ env, request: request() });
    const row = await env.DB.prepare("select publish_state from submissions where submission_id = 'ticket_fixture_migration'").first();
    const stored = await env.SUBMISSIONS.get("board/community-live.json");
    const board = stored === null ? null : await new Response(stored.body).json();
    expect(await first.json()).toMatchObject({ migrated_count: 1 });
    expect(await second.json()).toMatchObject({ migrated_count: 0 });
    expect(row).toMatchObject({ publish_state: "published" });
    expect(board).toMatchObject({ rows: [{ submission_id: "ticket_fixture_migration" }] });
  });
});

async function boardEnv() {
  return createEnv({
    includeAdminSecret: true,
    includeR2Secrets: true,
    migrations: [
      MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
      MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012, MIGRATION_0013, MIGRATION_0014,
      MIGRATION_0015, MIGRATION_0017,
    ],
  });
}

type BoardFixture = {
  readonly githubLogin?: string;
  readonly projectionMissing?: boolean;
  readonly publishedAt: string;
  readonly rawSha?: string;
  readonly submissionId: string;
};

async function insertBoardFixture(env: Awaited<ReturnType<typeof boardEnv>>, fixture: BoardFixture): Promise<void> {
  const rawSha = fixture.rawSha ?? RAW_BUNDLE_SHA;
  const update = statusUpdate("accepted", rawSha, "community");
  const projection = AcceptedResultProjectionV2Schema.parse(update["projection"]);
  const objectSha = await sha256Hex(canonicalJson(projection));
  if (fixture.projectionMissing !== true) {
    await env.SUBMISSIONS.put(projectionKey(objectSha), canonicalJson(projection));
  }
  await env.DB.prepare(
    `insert into submissions (
      submission_id, origin, submitter_id, submitter_display_name, github_login, status, raw_bundle_sha256,
      idempotency_key, publish_state, published_at, validated_at, suite_release_id,
      suite_manifest_sha256, projection_sha256, projection_object_sha256, projection_r2_key,
      community_model_group_id, state_revision, zt1_decision, zt1_coding_state
    ) values (?, 'community', ?, 'Fixture Submitter', ?, 'accepted', ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, 1, 'publishable', 'self_reported_exec')`,
  ).bind(
    fixture.submissionId, `public_key:${"d".repeat(64)}`, fixture.githubLogin ?? null, rawSha, rawSha,
    fixture.publishedAt, "2026-07-18 00:00:00", SUITE_RELEASE_ID, SUITE_MANIFEST_SHA,
    projection.artifact_hashes.projection_sha256, objectSha, projectionKey(objectSha),
    TEST_COMMUNITY_GROUP_ID,
  ).run();
}

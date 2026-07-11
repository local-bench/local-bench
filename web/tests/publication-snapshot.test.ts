import { describe, expect, it } from "vitest";
import {
  handleActivatePublicationSnapshot,
  handleCreatePublicationSnapshot,
  handleExportPublicationSnapshot,
  SUPPRESSION_MAX_EXPOSURE_SECONDS,
} from "../functions/_lib/publication-snapshot";
import { transitionAcceptedToTerminal } from "../functions/_lib/submission-store";
import { persistProjectionCreateOnly } from "../functions/_lib/publication-storage";
import {
  ADMIN_SECRET, MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
  MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, PROJECTION_OBJECT_SHA, SUITE_MANIFEST_SHA,
  SUITE_RELEASE_ID, createEnv, getRequest, jsonRequest,
} from "./submission-test-support";

const MIGRATIONS = [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011];

describe("immutable publication snapshots", () => {
  it("materializes one epoch and exports stable complete pagination", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
    await insertPublished(env, "sub_b", "community-group:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    await insertPublished(env, "sub_a", "community-group:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    const created = await handleCreatePublicationSnapshot(adminPost("/api/admin/publication-snapshot"), env);
    expect(created.status).toBe(201);
    const snapshot = await created.json();
    expect(snapshot.total_count).toBe(2);
    expect(snapshot.rows.map((row: { submission_id: string }) => row.submission_id)).toEqual(["sub_a", "sub_b"]);

    await env.DB.prepare("update submissions set publish_state = 'hidden' where submission_id = 'sub_a'").run();
    const exported = await handleExportPublicationSnapshot(
      getRequest(`/api/admin/publication-snapshot?snapshot_id=${snapshot.snapshot_id}&cursor=0`, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
    );
    const page = await exported.json();
    expect(page.total_count).toBe(2);
    expect(page.rows).toEqual(snapshot.rows);
    expect(page.next_cursor).toBeNull();
  });

  it("blocks activation when suppression lands after the snapshot", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
    await insertPublished(env, "sub_suppressed", "community-group:cccccccccccccccccccccccccccccccc");
    const created = await handleCreatePublicationSnapshot(adminPost("/api/admin/publication-snapshot"), env);
    const snapshot = await created.json();
    await transitionAcceptedToTerminal(env, "sub_suppressed", "suppressed", "security removal");
    const activation = await handleActivatePublicationSnapshot(
      jsonRequest("/api/admin/publication-snapshot?action=activate", { snapshot_id: snapshot.snapshot_id, publication_revision: snapshot.publication_revision }, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
    );
    expect(activation.status).toBe(409);
    expect(await activation.json()).toMatchObject({ code: "publication_revision_mismatch" });
    expect(SUPPRESSION_MAX_EXPOSURE_SECONDS).toBe(300);
  });

  it("rejects a projection overwrite attempt at a referenced content address", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const declared = "d".repeat(64);
    await env.SUBMISSIONS.put(`projections/sha256/${declared}.json`, "original");
    await expect(persistProjectionCreateOnly(env, declared, "mutated")).rejects.toThrow("collision or mutation");
    const stored = await env.SUBMISSIONS.get(`projections/sha256/${declared}.json`);
    expect(stored === null ? null : await new Response(stored.body).text()).toBe("original");
  });
});

async function insertPublished(env: Awaited<ReturnType<typeof createEnv>>, id: string, groupId: string): Promise<void> {
  const digest = id === "sub_a" ? "a".repeat(64) : id === "sub_b" ? "b".repeat(64) : PROJECTION_OBJECT_SHA;
  await env.DB.prepare(
    `insert into submissions (submission_id, origin, status, raw_bundle_sha256, idempotency_key, publish_state,
      projection_object_sha256, projection_r2_key, suite_release_id, suite_manifest_sha256, community_model_group_id,
      zt1_decision, zt1_coding_state, validated_at)
     values (?, 'community', 'accepted', ?, ?, 'published', ?, ?, ?, ?, ?, 'publishable', 'verifier', '2026-07-12 00:00:00')`,
  ).bind(id, digest, digest, digest, `projections/sha256/${digest}.json`, SUITE_RELEASE_ID, SUITE_MANIFEST_SHA, groupId).run();
}

function adminPost(path: string): Request {
  return new Request(`https://local-bench.ai${path}`, { method: "POST", headers: { "x-localbench-admin-secret": ADMIN_SECRET } });
}

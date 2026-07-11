import { adminBlocked, jsonResponse } from "./submission-api-support";
import { canonicalJson, sha256Hex } from "./submission-canonical";
import type { D1PreparedStatement, SubmissionApiEnv } from "./submission-contracts";

export const SUPPRESSION_MAX_EXPOSURE_SECONDS = 300;
const PAGE_LIMIT = 100;

type SnapshotRow = {
  readonly community_model_group_id: string;
  readonly decision_class: string;
  readonly ordinal: number;
  readonly projection_object_sha256: string;
  readonly projection_r2_key: string;
  readonly publish_state: string;
  readonly state_revision: number;
  readonly submission_id: string;
  readonly suite_manifest_sha256: string;
  readonly suite_release_id: string;
  readonly trust_class: string;
};

export async function handleCreatePublicationSnapshot(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  if (env.DB.batch === undefined) return jsonResponse(503, { code: "d1_batch_required", error: "snapshot creation requires D1 batch" });
  const snapshotId = `pub_${crypto.randomUUID().replaceAll("-", "")}`;
  const createdAt = new Date().toISOString();
  const statements: D1PreparedStatement[] = [
    env.DB.prepare(
      `insert into publication_snapshots (snapshot_id, publication_revision, snapshot_digest, total_count, created_at)
       select ?, publication_revision, 'pending', 0, ? from publication_control where singleton = 1`,
    ).bind(snapshotId, createdAt),
    env.DB.prepare(
      `insert into publication_snapshot_rows (
        snapshot_id, ordinal, submission_id, projection_object_sha256, projection_r2_key,
        publish_state, state_revision, suite_release_id, suite_manifest_sha256,
        decision_class, trust_class, community_model_group_id
      )
      select ?, row_number() over (order by coalesce(validated_at, created_at) asc, submission_id asc),
        submission_id, projection_object_sha256, projection_r2_key, publish_state, state_revision,
        suite_release_id, suite_manifest_sha256, coalesce(zt1_decision, 'maintainer'),
        coalesce(zt1_coding_state, 'unverified'), community_model_group_id
      from submissions
      where status = 'accepted' and origin = 'community' and publish_state in ('preview', 'published')
        and projection_object_sha256 is not null and projection_r2_key is not null
        and community_model_group_id is not null and coalesce(zt1_decision, '') <> 'escalated'
      order by coalesce(validated_at, created_at) asc, submission_id asc`,
    ).bind(snapshotId),
  ];
  await env.DB.batch(statements);
  const rows = await snapshotRows(env, snapshotId);
  const digest = await sha256Hex(canonicalJson(rows));
  await env.DB.prepare(
    "update publication_snapshots set snapshot_digest = ?, total_count = ? where snapshot_id = ? and snapshot_digest = 'pending'",
  ).bind(digest, rows.length, snapshotId).run();
  const snapshot = await snapshotHeader(env, snapshotId);
  return jsonResponse(201, { ...snapshot, rows });
}

export async function handleExportPublicationSnapshot(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  const url = new URL(request.url);
  const snapshotId = url.searchParams.get("snapshot_id");
  const cursor = Number(url.searchParams.get("cursor") ?? "0");
  if (snapshotId === null || !Number.isInteger(cursor) || cursor < 0) {
    return jsonResponse(400, { code: "invalid_snapshot_cursor", error: "snapshot_id and a non-negative cursor are required" });
  }
  const header = await snapshotHeader(env, snapshotId);
  if (header === null || header["snapshot_digest"] === "pending") return jsonResponse(404, { code: "snapshot_not_found", error: "publication snapshot not found" });
  const allRows = await snapshotRows(env, snapshotId);
  const rows = allRows.slice(cursor, cursor + PAGE_LIMIT);
  const nextCursor = cursor + rows.length < allRows.length ? cursor + rows.length : null;
  return jsonResponse(200, { ...header, cursor, next_cursor: nextCursor, rows });
}

export async function handleActivatePublicationSnapshot(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  const body: unknown = await request.json();
  if (!isRecord(body) || typeof body["snapshot_id"] !== "string" || typeof body["publication_revision"] !== "number") {
    return jsonResponse(400, { code: "invalid_activation", error: "snapshot_id and publication_revision are required" });
  }
  const result = await env.DB.prepare(
    `update publication_control set active_snapshot_id = ?, updated_at = datetime('now')
     where singleton = 1 and publication_revision = ?
       and not exists (
         select 1 from publication_edge_blocks b
         join publication_snapshot_rows r on r.submission_id = b.submission_id
         where r.snapshot_id = ?
       )`,
  ).bind(body["snapshot_id"], body["publication_revision"], body["snapshot_id"]).run();
  if (result.meta?.changes !== 1) {
    return jsonResponse(409, { code: "publication_revision_mismatch", error: "publication changed after snapshot; rebuild required" });
  }
  await env.DB.prepare("update publication_snapshots set activated_at = datetime('now') where snapshot_id = ?")
    .bind(body["snapshot_id"]).run();
  return jsonResponse(200, { active_snapshot_id: body["snapshot_id"], publication_revision: body["publication_revision"] });
}

async function snapshotRows(env: SubmissionApiEnv, snapshotId: string): Promise<readonly SnapshotRow[]> {
  const result = await env.DB.prepare(
    `select ordinal, submission_id, projection_object_sha256, projection_r2_key, publish_state,
      state_revision, suite_release_id, suite_manifest_sha256, decision_class, trust_class,
      community_model_group_id from publication_snapshot_rows where snapshot_id = ? order by ordinal asc`,
  ).bind(snapshotId).all();
  return result.results.map((row) => ({
    community_model_group_id: text(row, "community_model_group_id"), decision_class: text(row, "decision_class"),
    ordinal: number(row, "ordinal"), projection_object_sha256: text(row, "projection_object_sha256"),
    projection_r2_key: text(row, "projection_r2_key"), publish_state: text(row, "publish_state"),
    state_revision: number(row, "state_revision"), submission_id: text(row, "submission_id"),
    suite_manifest_sha256: text(row, "suite_manifest_sha256"), suite_release_id: text(row, "suite_release_id"),
    trust_class: text(row, "trust_class"),
  }));
}

async function snapshotHeader(env: SubmissionApiEnv, snapshotId: string): Promise<Record<string, unknown> | null> {
  return env.DB.prepare(
    "select snapshot_id, publication_revision, snapshot_digest, total_count, created_at from publication_snapshots where snapshot_id = ?",
  ).bind(snapshotId).first();
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key]; if (typeof value !== "string") throw new Error(`${key} must be a string`); return value;
}
function number(row: Record<string, unknown>, key: string): number {
  const value = row[key]; if (typeof value !== "number") throw new Error(`${key} must be a number`); return value;
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

import { AcceptedResultProjectionV2Schema, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, jsonResponse } from "./submission-api-support";
import { clientIp, parseJson } from "./submission-api-common";
import { canonicalJson, sha256Hex } from "./submission-canonical";
import { rateLimited } from "./submission-rate-limit";
import { projectionKey } from "./submission-storage";
import { githubAttributionAvailable } from "./github-oauth-store";
import { isCompleteProjection, projectionComposite } from "./submission-publish-validation";

export const COMMUNITY_LIVE_BOARD_KEY = "board/community-live.json";
const BOARD_CACHE_SECONDS = 60;
const BOARD_MISSES_PER_IP_PER_MINUTE = 30;
const BOARD_ROW_LIMIT = 500;

type EligibleRow = {
  readonly communityModelGroupId: string | null;
  readonly createdAt: string;
  readonly githubLogin: string | null;
  readonly origin: "community" | "project_anchor";
  readonly projectionObjectSha256: string;
  readonly publishedAt: string;
  readonly submissionId: string;
  readonly submitterDisplayName: string | null;
  readonly submitterId: string | null;
  readonly validatedAt: string;
};

type AcceptedProjection = ReturnType<typeof AcceptedResultProjectionV2Schema.parse>;

export async function rebuildCommunityLiveBoard(env: SubmissionApiEnv) {
  const [eligible, control] = await Promise.all([
    eligibleRows(env),
    env.DB.prepare(
      "select publication_revision, edge_block_revision from publication_control where singleton = 1",
    ).first(),
  ]);
  const materialized: Array<{ readonly complete: boolean; readonly projection: AcceptedProjection; readonly row: EligibleRow }> = [];
  let omittedRows = 0;
  for (const row of eligible) {
    const projection = await loadProjection(env, row.projectionObjectSha256);
    if (projection === null) {
      omittedRows += 1;
      continue;
    }
    materialized.push({ complete: isCompleteProjection(projection), projection, row });
  }
  materialized.sort((left, right) =>
    Number(right.complete) - Number(left.complete)
      || projectionComposite(right.projection) - projectionComposite(left.projection)
      || left.row.submissionId.localeCompare(right.row.submissionId));
  const rows = materialized.map(({ complete, projection, row }) => liveBoardRow(row, projection, complete));
  const withoutDigest = {
    edge_block_revision: numericOrZero(control?.["edge_block_revision"]),
    generated_at: new Date().toISOString(),
    omitted_rows: omittedRows,
    publication_revision: numericOrZero(control?.["publication_revision"]),
    rows,
    schema_version: "localbench.community_live_board.v1",
  } as const;
  const payload = {
    ...withoutDigest,
    board_digest: await sha256Hex(canonicalJson(withoutDigest)),
  };
  await env.SUBMISSIONS.put(COMMUNITY_LIVE_BOARD_KEY, canonicalJson(payload));
  return payload;
}

export async function handleCommunityLiveBoard(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const url = new URL(request.url);
  if (url.search.length > 0) {
    return jsonResponse(400, { code: "query_parameters_not_allowed", error: "community board does not accept query parameters" });
  }
  const cache = edgeCache();
  const cacheKey = new Request(new URL("/api/board/community.json", request.url));
  const cached = cache === null ? undefined : await cache.match(cacheKey);
  if (cached !== undefined) return cached;
  const limit = await rateLimited(env, `community-board:ip:${clientIp(request)}`, BOARD_MISSES_PER_IP_PER_MINUTE, 60);
  if (limit.limited) {
    return Response.json({ code: "rate_limited", retry_after_seconds: limit.retryAfterSeconds }, {
      headers: { "cache-control": "no-store", "retry-after": String(limit.retryAfterSeconds) },
      status: 429,
    });
  }
  const stored = await env.SUBMISSIONS.get(COMMUNITY_LIVE_BOARD_KEY);
  const body = stored === null
    ? canonicalJson(await rebuildCommunityLiveBoard(env))
    : await new Response(stored.body).text();
  const response = new Response(body, {
    headers: {
      "cache-control": `public, max-age=0, s-maxage=${BOARD_CACHE_SECONDS}`,
      "content-type": "application/json",
    },
    status: 200,
  });
  if (cache !== null) await cache.put(cacheKey, response.clone());
  return response;
}

export async function handleAdminCommunityBoardRebuild(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) return blocked;
  return jsonResponse(200, await rebuildCommunityLiveBoard(env));
}

async function eligibleRows(env: SubmissionApiEnv): Promise<readonly EligibleRow[]> {
  const hasGithubAttribution = await githubAttributionAvailable(env);
  const result = await env.DB.prepare(
    `select s.submission_id, s.submitter_id, s.submitter_display_name,
      ${hasGithubAttribution ? "s.github_login" : "null as github_login"}, s.created_at,
      s.validated_at, s.published_at, s.projection_object_sha256,
      s.community_model_group_id, s.origin
     from submissions s
     where (s.status = 'published' or (s.status = 'accepted' and s.publish_state = 'published'))
       and s.projection_object_sha256 is not null
       and not exists (select 1 from publication_edge_blocks b where b.submission_id = s.submission_id)
     order by s.published_at desc, s.submission_id asc
     limit ?`,
  ).bind(BOARD_ROW_LIMIT).all();
  return result.results.map((row) => ({
    communityModelGroupId: nullableText(row, "community_model_group_id"),
    createdAt: text(row, "created_at"),
    githubLogin: nullableText(row, "github_login"),
    origin: submissionOrigin(row),
    projectionObjectSha256: text(row, "projection_object_sha256"),
    publishedAt: text(row, "published_at"),
    submissionId: text(row, "submission_id"),
    submitterDisplayName: nullableText(row, "submitter_display_name"),
    submitterId: nullableText(row, "submitter_id"),
    validatedAt: text(row, "validated_at"),
  }));
}

function liveBoardRow(
  row: EligibleRow,
  projection: ReturnType<typeof AcceptedResultProjectionV2Schema.parse>,
  complete: boolean,
) {
  return {
    axes: projection.axes,
    ...(row.communityModelGroupId === null ? {} : {
      community_model_group_id: row.communityModelGroupId,
      group_path: `community/groups/${row.communityModelGroupId.slice("community-group:".length)}.json`,
    }),
    conformance: projection.conformance,
    coverage_profile_id: projection.coverage_profile_id,
    headline_complete: projection.headline_complete,
    index_version: projection.index_version ?? null,
    lineage: projection.lineage,
    model: {
      declared_name: projection.model.declared_name,
      display_name: projection.model.display_name,
      family: projection.model.family ?? null,
      file_sha256: projection.model.file_sha256,
      ...(projection.model.hf === undefined ? {} : { hf: projection.model.hf }),
      model_system_key: projection.model.model_system_key,
      quant_label: projection.model.quant_label ?? null,
    },
    origin: row.origin,
    ...(row.origin === "project_anchor" ? { badge: "project-run" } : {}),
    normalization_annotations: projection.normalization_annotations ?? [],
    provenance_notes: projection.provenance_notes ?? [],
    receipt_references: projection.receipt_references,
    ranked: complete,
    rescore_modes: projection.rescore_modes,
    scorecard_id: projection.scorecard_id,
    scores: projection.scores,
    submission_id: row.submissionId,
    submitter: {
      github_login: row.githubLogin,
      key_fingerprint: keyFingerprint(row.submitterId),
      unverified_handle: row.submitterDisplayName,
    },
    suite_release_id: projection.suite_release_id,
    timestamps: {
      published_at: d1TimestampToIso(row.publishedAt),
      submitted_at: d1TimestampToIso(row.createdAt),
      validated_at: d1TimestampToIso(row.validatedAt),
    },
  } as const;
}

function submissionOrigin(row: Record<string, unknown>): "community" | "project_anchor" {
  const value = row["origin"];
  if (value === "community" || value === "project_anchor") return value;
  throw new Error("origin must be a submission origin");
}

async function loadProjection(
  env: SubmissionApiEnv,
  objectSha256: string,
): Promise<ReturnType<typeof AcceptedResultProjectionV2Schema.parse> | null> {
  try {
    const object = await env.SUBMISSIONS.get(projectionKey(objectSha256));
    if (object === null) return null;
    const parsed = AcceptedResultProjectionV2Schema.safeParse(parseJson(await new Response(object.body).text()));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function edgeCache(): Cache | null {
  const value = (globalThis as typeof globalThis & { readonly caches?: CacheStorage & { readonly default?: Cache } }).caches;
  return value?.default ?? null;
}

function keyFingerprint(submitterId: string | null): string | null {
  if (submitterId === null || !/^public_key:[0-9a-f]{64}$/.test(submitterId)) return null;
  return submitterId.slice("public_key:".length, "public_key:".length + 12);
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? `${value.slice(0, 10)}T${value.slice(11)}Z` : value;
}

function numericOrZero(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") throw new Error(`${key} must be a string`);
  return value;
}

function nullableText(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value === null || typeof value === "string") return value;
  throw new Error(`${key} must be a string or null`);
}

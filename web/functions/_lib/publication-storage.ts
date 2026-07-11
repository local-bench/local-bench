import type { SubmissionApiEnv } from "./submission-contracts";
import { sha256Hex } from "./submission-canonical";
import { projectionKey } from "./submission-storage";

export async function persistProjectionCreateOnly(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  canonicalBytes: string,
): Promise<string> {
  const key = projectionKey(projectionObjectSha256);
  if (await sha256Hex(canonicalBytes) !== projectionObjectSha256) {
    throw new Error("projection content address does not match canonical bytes");
  }
  let putError: unknown = null;
  try {
    await env.SUBMISSIONS.put(key, canonicalBytes, { onlyIf: { etagDoesNotMatch: "*" } });
  } catch (error) {
    putError = error;
  }
  const stored = await env.SUBMISSIONS.get(key);
  if (stored === null) {
    if (putError !== null) throw putError;
    throw new Error("projection object missing after create-only put");
  }
  const bytes = await new Response(stored.body).text();
  if (bytes !== canonicalBytes) throw new Error("projection object collision or mutation");
  return key;
}

/** Projection content addresses are append-only for their entire lifetime. */
export async function overwriteProjectionObject(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  canonicalBytes: string,
): Promise<void> {
  await assertProjectionUnreferenced(env, projectionObjectSha256, "overwrite");
  if (await sha256Hex(canonicalBytes) !== projectionObjectSha256) {
    throw new Error("projection content address does not match canonical bytes");
  }
  await env.SUBMISSIONS.put(projectionKey(projectionObjectSha256), canonicalBytes);
}

/** Referenced projections have no deletion contract; retention is permanent. */
export async function deleteProjectionObject(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
): Promise<void> {
  await assertProjectionUnreferenced(env, projectionObjectSha256, "deletion");
  await env.SUBMISSIONS.delete(projectionKey(projectionObjectSha256));
}

async function assertProjectionUnreferenced(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  operation: "overwrite" | "deletion",
): Promise<void> {
  const reference = await env.DB.prepare(
    `select 1 as referenced from submissions where projection_object_sha256 = ?
     union all
     select 1 as referenced from publication_snapshot_rows where projection_object_sha256 = ?
     limit 1`,
  ).bind(projectionObjectSha256, projectionObjectSha256).first();
  if (reference !== null) {
    throw new Error(`projection storage fence: ${operation} is prohibited after reference`);
  }
}

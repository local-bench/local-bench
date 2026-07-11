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

export async function persistProjectionAndReference<T>(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  canonicalBytes: string,
  establishReference: (projectionR2Key: string) => Promise<T>,
): Promise<T> {
  return withStorageFence(env, projectionObjectSha256, "reference", async () => {
    const key = await persistProjectionCreateOnly(env, projectionObjectSha256, canonicalBytes);
    return establishReference(key);
  });
}

/** Projection content addresses are append-only for their entire lifetime. */
export async function overwriteProjectionObject(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  canonicalBytes: string,
): Promise<void> {
  await withUnreferencedStorageFence(env, projectionObjectSha256, "overwrite", async () => {
    if (await sha256Hex(canonicalBytes) !== projectionObjectSha256) {
      throw new Error("projection content address does not match canonical bytes");
    }
    await env.SUBMISSIONS.put(projectionKey(projectionObjectSha256), canonicalBytes);
  });
}

/** Referenced projections have no deletion contract; retention is permanent. */
export async function deleteProjectionObject(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  hooks: { readonly afterFence?: () => Promise<void> } = {},
): Promise<void> {
  await withUnreferencedStorageFence(env, projectionObjectSha256, "deletion", async () => {
    await hooks.afterFence?.();
    await env.SUBMISSIONS.delete(projectionKey(projectionObjectSha256));
  });
}

async function withUnreferencedStorageFence<T>(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  operation: "overwrite" | "deletion",
  action: () => Promise<T>,
): Promise<T> {
  const owner = `${operation}:${crypto.randomUUID()}`;
  const claimed = await env.DB.prepare(
    `insert into projection_storage_fences (projection_object_sha256, owner)
     select ?, ? where not exists (
       select 1 from submissions where projection_object_sha256 = ?
       union all
       select 1 from publication_snapshot_rows where projection_object_sha256 = ?
     ) on conflict(projection_object_sha256) do nothing`,
  ).bind(projectionObjectSha256, owner, projectionObjectSha256, projectionObjectSha256).run();
  if (claimed.meta?.changes === 1) {
    try {
      return await action();
    } finally {
      await releaseStorageFence(env, projectionObjectSha256, owner);
    }
  }
  const reference = await env.DB.prepare(
    `select 1 as referenced from submissions where projection_object_sha256 = ?
     union all
     select 1 as referenced from publication_snapshot_rows where projection_object_sha256 = ?
     limit 1`,
  ).bind(projectionObjectSha256, projectionObjectSha256).first();
  if (reference !== null) {
    throw new Error(`projection storage fence: ${operation} is prohibited after reference`);
  }
  throw new Error(`projection storage fence: ${operation} conflicts with an in-flight reference`);
}

async function withStorageFence<T>(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  operation: "reference",
  action: () => Promise<T>,
): Promise<T> {
  const owner = `${operation}:${crypto.randomUUID()}`;
  const claimed = await env.DB.prepare(
    `insert into projection_storage_fences (projection_object_sha256, owner)
     values (?, ?) on conflict(projection_object_sha256) do nothing`,
  ).bind(projectionObjectSha256, owner).run();
  if (claimed.meta?.changes !== 1) {
    throw new Error("projection storage fence: reference conflicts with an in-flight mutation");
  }
  try {
    return await action();
  } finally {
    await releaseStorageFence(env, projectionObjectSha256, owner);
  }
}

async function releaseStorageFence(env: SubmissionApiEnv, projectionObjectSha256: string, owner: string): Promise<void> {
  await env.DB.prepare(
    "delete from projection_storage_fences where projection_object_sha256 = ? and owner = ?",
  ).bind(projectionObjectSha256, owner).run();
}

import type { SubmissionApiEnv } from "./submission-contracts";
import { projectionKey } from "./submission-storage";

export async function persistProjectionCreateOnly(
  env: SubmissionApiEnv,
  projectionObjectSha256: string,
  canonicalBytes: string,
): Promise<string> {
  const key = projectionKey(projectionObjectSha256);
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

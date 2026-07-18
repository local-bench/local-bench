import { jsonResponse } from "./submission-api-support";
import { canonicalJson, sha256Hex } from "./submission-canonical";
import type { StatusUpdate, SubmissionRow } from "./submission-contracts";

type AcceptedUpdate = Extract<StatusUpdate, { readonly status: "accepted" }>;

export type ProjectionValidation =
  | { readonly canonicalBytes: string; readonly kind: "valid" }
  | { readonly kind: "invalid"; readonly response: Response };

export async function validateAcceptedProjection(
  update: AcceptedUpdate,
  row: SubmissionRow,
): Promise<ProjectionValidation> {
  const canonicalBytes = canonicalJson(update.projection);
  const objectSha256 = await sha256Hex(canonicalBytes);
  if (objectSha256 !== update.projection_object_sha256) {
    return invalid(409, "projection_object_sha_mismatch", "projection bytes do not match projection_object_sha256");
  }
  if (update.projection.artifact_hashes.projection_sha256 !== update.projection_sha256) {
    return invalid(409, "projection_semantic_sha_mismatch", "projection semantic digest does not match status update");
  }
  if (
    update.projection.origin !== row.origin ||
    update.projection.suite_release_id !== row.suite_release_id ||
    update.projection.suite_manifest_sha256 !== row.suite_manifest_sha256
  ) {
    return invalid(409, "projection_scope_mismatch", "projection suite pair or origin does not match the submission");
  }
  const semanticProjection = structuredClone(update.projection);
  semanticProjection.artifact_hashes.projection_sha256 = "";
  semanticProjection.artifact_hashes.public_artifact_manifest_sha256 = "";
  const semanticSha256 = await sha256Hex(canonicalJson(semanticProjection));
  if (semanticSha256 !== update.projection_sha256) {
    return invalid(409, "projection_semantic_sha_mismatch", "projection blank-field semantic digest is invalid");
  }
  const publicManifestSha256 = await sha256Hex(canonicalJson({
    bundle_sha256: row.raw_bundle_sha256,
    projection_sha256: semanticSha256,
  }));
  if (
    update.projection.artifact_hashes.bundle_sha256 !== row.raw_bundle_sha256 ||
    update.projection.artifact_hashes.public_artifact_manifest_sha256 !== publicManifestSha256
  ) {
    return invalid(409, "projection_artifact_mismatch", "projection artifact digest binding is invalid");
  }
  return { canonicalBytes, kind: "valid" };
}

function invalid(status: number, code: string, error: string): ProjectionValidation {
  return { kind: "invalid", response: jsonResponse(status, { code, error }) };
}

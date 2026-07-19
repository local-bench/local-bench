import { jsonResponse } from "./submission-api-support";
import { canonicalJson, sha256Hex } from "./submission-canonical";
import type { AcceptedResultProjectionV2Schema } from "./accepted-result-projection-contract";
import type { StatusUpdate, SubmissionRow } from "./submission-contracts";
import { indexV42Composite } from "./submission-publish-validation";
import type { z } from "zod";

type AcceptedUpdate = Extract<StatusUpdate, { readonly status: "accepted" }>;

export type ProjectionValidation =
  | { readonly canonicalBytes: string; readonly kind: "valid"; readonly objectSha256: string; readonly projection: AcceptedProjection }
  | { readonly kind: "invalid"; readonly response: Response };

type AcceptedProjection = z.infer<typeof AcceptedResultProjectionV2Schema>;

export async function validateAcceptedProjection(
  update: AcceptedUpdate,
  row: SubmissionRow,
): Promise<ProjectionValidation> {
  return validateProjectionBindings(
    update.projection,
    update.projection_object_sha256,
    update.projection_sha256,
    row,
  );
}

export async function validateSubmittedProjection(
  projection: AcceptedProjection,
  row: SubmissionRow,
): Promise<ProjectionValidation> {
  const canonicalBytes = canonicalJson(projection);
  const objectSha256 = await sha256Hex(canonicalBytes);
  const clientValidation = await validateProjectionBindings(
    projection,
    objectSha256,
    projection.artifact_hashes.projection_sha256,
    row,
  );
  if (clientValidation.kind === "invalid") return clientValidation;
  return normalizedProjection(projection, row.raw_bundle_sha256);
}

async function validateProjectionBindings(
  projection: AcceptedProjection,
  expectedObjectSha256: string,
  expectedProjectionSha256: string,
  row: SubmissionRow,
): Promise<ProjectionValidation> {
  const canonicalBytes = canonicalJson(projection);
  const objectSha256 = await sha256Hex(canonicalBytes);
  if (objectSha256 !== expectedObjectSha256) {
    return invalid(409, "projection_object_sha_mismatch", "projection bytes do not match projection_object_sha256");
  }
  if (projection.artifact_hashes.projection_sha256 !== expectedProjectionSha256) {
    return invalid(409, "projection_semantic_sha_mismatch", "projection semantic digest does not match status update");
  }
  if (
    projection.origin !== row.origin ||
    projection.suite_release_id !== row.suite_release_id ||
    projection.suite_manifest_sha256 !== row.suite_manifest_sha256
  ) {
    return invalid(409, "projection_scope_mismatch", "projection suite pair or origin does not match the submission");
  }
  const semanticProjection = structuredClone(projection);
  semanticProjection.artifact_hashes.projection_sha256 = "";
  semanticProjection.artifact_hashes.public_artifact_manifest_sha256 = "";
  const semanticSha256 = await sha256Hex(canonicalJson(semanticProjection));
  if (semanticSha256 !== expectedProjectionSha256) {
    return invalid(409, "projection_semantic_sha_mismatch", "projection blank-field semantic digest is invalid");
  }
  const publicManifestSha256 = await sha256Hex(canonicalJson({
    bundle_sha256: row.raw_bundle_sha256,
    projection_sha256: semanticSha256,
  }));
  if (
    projection.artifact_hashes.bundle_sha256 !== row.raw_bundle_sha256 ||
    projection.artifact_hashes.public_artifact_manifest_sha256 !== publicManifestSha256
  ) {
    return invalid(409, "projection_artifact_mismatch", "projection artifact digest binding is invalid");
  }
  return { canonicalBytes, kind: "valid", objectSha256, projection };
}

type CompositeField = "headline_score" | "partial_composite" | "composite_full";

async function normalizedProjection(
  projection: AcceptedProjection,
  rawBundleSha256: string,
): Promise<ProjectionValidation> {
  const serverValue = indexV42Composite(projection);
  const clientValues = {
    composite_full: projection.scores.composite_full ?? null,
    headline_score: projection.scores.headline_score,
    partial_composite: projection.scores.partial_composite,
  };
  const driftFields: CompositeField[] = [];
  if (drifted(clientValues.headline_score, serverValue)) driftFields.push("headline_score");
  if (drifted(clientValues.partial_composite, serverValue)) driftFields.push("partial_composite");
  if (drifted(clientValues.composite_full, serverValue)) driftFields.push("composite_full");
  const normalizationAnnotations = driftFields.length === 0 ? [] : [{
    client_values: clientValues,
    code: "client_composite_drift" as const,
    fields: driftFields,
    server_value: serverValue,
  }];
  const hashableProjection: AcceptedProjection = {
    ...projection,
    artifact_hashes: {
      bundle_sha256: rawBundleSha256,
      projection_sha256: "",
      public_artifact_manifest_sha256: "",
    },
    normalization_annotations: normalizationAnnotations,
    scores: {
      ...projection.scores,
      composite_full: serverValue,
      headline_score: serverValue,
      known_headline_contribution: serverValue,
      partial_composite: serverValue,
    },
  };
  const semanticSha256 = await sha256Hex(canonicalJson(hashableProjection));
  const normalized: AcceptedProjection = {
    ...hashableProjection,
    artifact_hashes: {
      bundle_sha256: rawBundleSha256,
      projection_sha256: semanticSha256,
      public_artifact_manifest_sha256: await sha256Hex(canonicalJson({
        bundle_sha256: rawBundleSha256,
        projection_sha256: semanticSha256,
      })),
    },
  };
  const canonicalBytes = canonicalJson(normalized);
  return {
    canonicalBytes,
    kind: "valid",
    objectSha256: await sha256Hex(canonicalBytes),
    projection: normalized,
  };
}

function drifted(clientValue: number | null | undefined, serverValue: number): boolean {
  if (clientValue === null || clientValue === undefined) return true;
  const roundingTolerance = 0.0005 + Number.EPSILON * Math.max(1, Math.abs(clientValue), Math.abs(serverValue));
  return Math.abs(clientValue - serverValue) > roundingTolerance;
}

function invalid(status: number, code: string, error: string): ProjectionValidation {
  return { kind: "invalid", response: jsonResponse(status, { code, error }) };
}

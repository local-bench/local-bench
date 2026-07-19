import {
  DEFAULT_SUITE_MANIFEST_SHA256,
  DEFAULT_SUITE_RELEASE_ID,
  type SubmissionRow,
} from "./submission-contracts";
import { AcceptedResultProjectionV2Schema } from "./accepted-result-projection-contract";
import type { z } from "zod";

export const HEADLINE_AXES = [
  "agentic",
  "coding",
  "instruction_following",
  "knowledge",
  "math",
] as const;

export const HEADLINE_AXIS_COUNT = HEADLINE_AXES.length;

type HeadlineAxis = (typeof HEADLINE_AXES)[number];

const INDEX_V42_WEIGHTS: Readonly<Record<HeadlineAxis, number>> = {
  agentic: 0.25,
  coding: 0.225,
  instruction_following: 0.225,
  knowledge: 0.225,
  math: 0.075,
};

type Projection = z.infer<typeof AcceptedResultProjectionV2Schema>;

export type PublishProjectionRejection = "incomplete_run" | "schema_violation";

export function publishProjectionRejection(
  projection: Projection,
  row: SubmissionRow,
): PublishProjectionRejection | null {
  if (
    projection.suite_release_id !== DEFAULT_SUITE_RELEASE_ID ||
    projection.suite_manifest_sha256 !== DEFAULT_SUITE_MANIFEST_SHA256 ||
    projection.suite_release_id !== row.suite_release_id ||
    projection.suite_manifest_sha256 !== row.suite_manifest_sha256
  ) {
    return "schema_violation";
  }
  if (!isCompleteProjection(projection)) {
    return "incomplete_run";
  }
  if (
    projection.origin !== row.origin ||
    projection.verification_level !== "client_reported" ||
    (projection.origin === "community" && (
      projection.trust_label !== "community_self_submitted" || projection.agentic_provenance !== "self_reported"
    )) ||
    (projection.origin === "project_anchor" && projection.trust_label !== "project_anchor")
  ) {
    return "schema_violation";
  }
  return null;
}

export function isCompleteProjection(projection: Projection): boolean {
  return projection.suite_release_id === DEFAULT_SUITE_RELEASE_ID
    && projection.suite_manifest_sha256 === DEFAULT_SUITE_MANIFEST_SHA256
    && projection.coverage_profile_id === "full-exec-6axis-v1"
    && (projection.index_version === "index-v4.1" || projection.index_version === "index-v4.2")
    && projection.headline_complete
    && projection.scores.headline_score !== null
    && projection.scores.composite_full !== null
    && projection.scores.composite_full !== undefined
    && projection.scores.measured_headline_weight === 1
    && projection.scores.missing_headline_weight === 0
    && HEADLINE_AXES.every((axis) => {
      const value = projection.axes[axis];
      return value !== undefined && value.status === "measured" && value.score !== null && value.n > 0;
    });
}

export function projectionComposite(projection: Projection): number {
  if (isCompleteProjection(projection)) return indexV42Composite(projection);
  return projection.scores.composite_full ?? projection.scores.headline_score ?? projection.scores.partial_composite;
}

export function indexV42Composite(projection: Projection): number {
  const weighted = HEADLINE_AXES.reduce((total, axis) =>
    total + (projection.axes[axis]?.score ?? 0) * INDEX_V42_WEIGHTS[axis], 0);
  return Math.floor(weighted * 10_000 + 0.5) / 10_000;
}

import { executionProfilePolicy } from "./community-execution-profile-policy";
import { publicProvenanceNotes, publicRuntime } from "./community-live-board-public-row";
import { AcceptedResultProjectionV2Schema } from "./submission-contracts";

export type EligibleRow = {
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

const INDEX_VERSION_RELABELS: ReadonlyMap<string, { readonly from: string; readonly to: string }> = new Map([
  ["ticket_cc352811a58d4022b3044eb28abce178", { from: "index-v4.1", to: "index-v4.2" }],
]);

export function relabeledIndexVersion(submissionId: string, indexVersion: string | null): {
  readonly note: string | null;
  readonly value: string | null;
} {
  const relabel = INDEX_VERSION_RELABELS.get(submissionId);
  if (relabel === undefined || indexVersion !== relabel.from) return { note: null, value: indexVersion };
  return {
    note: `index_version_relabeled:${relabel.from}->${relabel.to}:maintainer:2026-07-22`,
    value: relabel.to,
  };
}

export function liveBoardRow(
  row: EligibleRow,
  projection: ReturnType<typeof AcceptedResultProjectionV2Schema.parse>,
  complete: boolean,
) {
  const indexVersion = relabeledIndexVersion(row.submissionId, projection.index_version ?? null);
  const profilePolicy = executionProfilePolicy({
    complete,
    hasHfIdentity: projection.model.hf !== undefined,
    runtimeName: projection.runtime?.name ?? null,
    structuredProfile: projection.execution_profile,
    submissionId: row.submissionId,
  });
  return {
    axes: projection.axes,
    ...(row.communityModelGroupId === null ? {} : {
      community_model_group_id: row.communityModelGroupId,
      group_path: `community/groups/${row.communityModelGroupId.slice("community-group:".length)}.json`,
    }),
    conformance: {
      ...(projection.conformance.n_scored === undefined ? {} : { n_scored: projection.conformance.n_scored }),
      ...(projection.conformance.reasons === undefined ? {} : { reasons: projection.conformance.reasons }),
      ...(projection.conformance.status === undefined ? {} : { status: projection.conformance.status }),
      ...(projection.conformance.worst_bench === undefined ? {} : { worst_bench: projection.conformance.worst_bench }),
    },
    coverage_profile_id: projection.coverage_profile_id,
    ...(profilePolicy.executionProfile === undefined ? {} : { execution_profile: profilePolicy.executionProfile }),
    headline_complete: projection.headline_complete,
    index_version: indexVersion.value,
    lineage: projection.lineage,
    ...(projection.runtime === undefined ? {} : { runtime: publicRuntime(projection.runtime) }),
    ...(projection.hardware === undefined ? {} : { hardware: projection.hardware }),
    ...(projection.perf === undefined ? {} : { perf: projection.perf }),
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
    ...(profilePolicy.moderationQueueMarker === undefined ? {} : {
      moderation_queue_marker: profilePolicy.moderationQueueMarker,
    }),
    provenance_notes: publicProvenanceNotes([
      ...(projection.provenance_notes ?? []),
      ...(indexVersion.note === null ? [] : [indexVersion.note]),
    ], profilePolicy.executionProfile),
    receipt_references: projection.receipt_references,
    ranked: complete && profilePolicy.moderationQueueMarker === undefined,
    rescore_modes: projection.rescore_modes,
    scorecard_id: projection.scorecard_id,
    scores: projection.scores,
    submission_id: row.submissionId,
    ...(profilePolicy.supersedesSubmissionId === undefined ? {} : {
      supersedes_submission_id: profilePolicy.supersedesSubmissionId,
    }),
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

function keyFingerprint(submitterId: string | null): string | null {
  if (submitterId === null || !/^public_key:[0-9a-f]{64}$/.test(submitterId)) return null;
  return submitterId.slice("public_key:".length, "public_key:".length + 12);
}

function d1TimestampToIso(value: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? `${value.slice(0, 10)}T${value.slice(11)}Z` : value;
}

import type { CommunityBoardRow } from "./community-data";
import {
  LiveBoardEnvelopeSchema,
  LiveBoardRowSchema,
  type LiveBoardRow,
} from "./community-live-schema";

export type { LiveBoardRow } from "./community-live-schema";

export type ParsedCommunityLiveBoard = {
  readonly droppedRows: number;
  readonly edgeBlockRevision: number;
  readonly generatedAt: string;
  readonly publicationRevision: number;
  readonly rows: readonly LiveBoardRow[];
};

export const LIVE_TRUST_TIER_LABELS: Readonly<Record<string, string>> = {
  community_re_scored: "re-scored",
  community_self_submitted: "self-reported",
  project_anchor: "maintainer-run",
};

export function trustTierLabel(trustLabel: string): string {
  return LIVE_TRUST_TIER_LABELS[trustLabel] ?? trustLabel;
}

export function parseCommunityLiveBoard(value: unknown): ParsedCommunityLiveBoard | null {
  const envelope = LiveBoardEnvelopeSchema.safeParse(value);
  if (!envelope.success) return null;
  const rows: LiveBoardRow[] = [];
  let droppedRows = envelope.data.omitted_rows;
  for (const valueRow of envelope.data.rows) {
    const row = LiveBoardRowSchema.safeParse(valueRow);
    if (row.success) rows.push(row.data);
    else droppedRows += 1;
  }
  return {
    droppedRows,
    edgeBlockRevision: envelope.data.edge_block_revision,
    generatedAt: envelope.data.generated_at,
    publicationRevision: envelope.data.publication_revision,
    rows,
  };
}

export function reconcileCommunityRows(
  baked: readonly CommunityBoardRow[],
  live: readonly LiveBoardRow[],
): readonly CommunityBoardRow[] {
  const bakedBySubmission = new Map(baked.map((row) => [row.submissionId, row]));
  const bakedGroupIds = new Set(
    baked.flatMap((row) => row.communityModelGroupId === undefined ? [] : [row.communityModelGroupId]),
  );
  return live.map((row) => mergeCommunityRow(bakedBySubmission.get(row.submission_id), row, bakedGroupIds));
}

function mergeCommunityRow(
  baked: CommunityBoardRow | undefined,
  live: LiveBoardRow,
  bakedGroupIds: ReadonlySet<string>,
): CommunityBoardRow {
  const groupSuffix = live.community_model_group_id.replace("community-group:", "");
  const bakedLineage = baked?.lineage;
  const lineage = bakedLineage ?? live.lineage_enrichment;
  return {
    artifactSha256: live.model.file_sha256,
    axes: live.axes,
    communityModelGroupId: live.community_model_group_id,
    declaredBaseModels: bakedLineage === undefined ? live.lineage.base_model : (baked?.declaredBaseModels ?? []),
    detailPath: bakedGroupIds.has(live.community_model_group_id) ? `/community/model/${groupSuffix}` : null,
    displayName: live.model.display_name ?? live.model.declared_name ?? "Community-declared variant",
    identityLabel: baked?.identityLabel ?? "community-declared, identity-unverified",
    lineage,
    live,
    measuredHeadlineWeight: live.scores.measured_headline_weight,
    missingHeadlineWeight: live.scores.missing_headline_weight,
    partialComposite: live.scores.partial_composite,
    quantLabel: live.model.quant_label,
    ranked: false,
    submissionId: live.submission_id,
    submitterDisplayName: live.submitter.display_name,
    submitterKeyFingerprint: live.submitter.key_fingerprint,
    timestamps: live.timestamps,
    trust: live.trust,
  };
}

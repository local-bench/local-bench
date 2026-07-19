import { z } from "zod";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
function safeText(maxCodePoints: number) {
  return z.string().refine((value) => [...value].length <= maxCodePoints, `must contain at most ${maxCodePoints} code points`)
    .refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}
const SAFE_TEXT = safeText(300);
const SCORE = z.number().finite().min(0).max(100);
const TIMESTAMP = z.string().refine((value) => !Number.isNaN(Date.parse(value)));
const AXIS = z.object({
  ci: z.tuple([SCORE, SCORE]).nullable().optional(),
  n: z.number().int().nonnegative().max(10_000_000).default(0),
  score: SCORE.nullable().optional(),
  status: z.enum(["measured", "not_measured", "invalid"]).default("measured"),
}).passthrough().readonly();
const AXES = z.record(SAFE_TEXT, AXIS).refine((axes) => Object.keys(axes).length <= 16);
const SCORES = z.object({
  composite: SCORE.nullable().optional(),
  composite_full: SCORE.nullable().optional(),
  headline_score: SCORE.nullable().optional(),
  measured_headline_weight: SCORE.optional(),
  missing_headline_weight: SCORE.optional(),
  partial_composite: SCORE.nullable().optional(),
}).passthrough().readonly();
const MODEL = z.object({
  declared_name: safeText(120).nullable().optional(),
  display_name: safeText(120).nullable().optional(),
  family: safeText(64).nullable().optional(),
  file_sha256: z.string().regex(/^[0-9a-f]{64}$/u),
  quant_label: safeText(32).nullable().optional(),
}).passthrough().readonly();
const SUBMITTER = z.object({
  display_name: safeText(80).nullable().optional(),
  github_login: z.string().regex(/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/u).nullable().optional(),
  key_fingerprint: z.string().regex(/^[0-9a-f]{12}$/u).nullable().optional(),
}).passthrough().readonly();
const TIMESTAMPS = z.object({
  published_at: TIMESTAMP,
  submitted_at: TIMESTAMP,
  validated_at: TIMESTAMP.optional(),
}).passthrough().readonly();
const LINEAGE = z.object({
  base_model: z.array(SAFE_TEXT).max(8).readonly().default([]),
}).passthrough().readonly();

export const LiveBoardRowSchema = z.object({
  axes: AXES,
  community_model_group_id: SAFE_TEXT,
  conformance: z.record(z.string(), z.unknown()).default({}),
  coverage_profile_id: SAFE_TEXT,
  group_path: SAFE_TEXT,
  headline_complete: z.boolean(),
  index_version: SAFE_TEXT.nullable(),
  lineage: LINEAGE,
  lineage_enrichment: z.record(z.string(), z.unknown()).optional(),
  model: MODEL,
  origin: z.enum(["community", "project_anchor"]),
  receipt_references: z.record(z.string(), z.unknown()).default({}),
  rescore_modes: z.record(z.string(), z.unknown()).default({}),
  scorecard_id: SAFE_TEXT,
  scores: SCORES,
  submission_id: SAFE_TEXT,
  submitter: SUBMITTER,
  suite_release_id: SAFE_TEXT,
  timestamps: TIMESTAMPS,
  trust: z.record(z.string(), z.unknown()).optional(),
}).passthrough().readonly();

const UnifiedBoardRowSchema = z.object({
  axes: AXES.default({}),
  community_model_group_id: SAFE_TEXT.optional(),
  global_rank: z.number().int().positive().nullable().optional(),
  headline_complete: z.boolean(),
  index_version: SAFE_TEXT.nullable().optional(),
  lineage: LINEAGE.optional(),
  lineage_enrichment: z.record(z.string(), z.unknown()).optional(),
  model: MODEL,
  origin: z.enum(["community", "project_anchor"]),
  rank: z.number().int().positive().nullable().optional(),
  scores: SCORES,
  submission_id: SAFE_TEXT,
  submitter: SUBMITTER.optional().default({}),
  timestamps: TIMESTAMPS.nullable().optional(),
  trust: z.record(z.string(), z.unknown()).optional(),
}).passthrough().readonly();

export const LiveBoardEnvelopeSchema = z.object({
  edge_block_revision: z.number().int().nonnegative().optional().default(0),
  generated_at: TIMESTAMP,
  omitted_rows: z.number().int().nonnegative().optional().default(0),
  publication_revision: z.number().int().nonnegative().optional().default(0),
  rows: z.array(z.unknown()).max(1_000).readonly(),
  schema_version: SAFE_TEXT.optional().default("localbench.board.v1"),
}).passthrough().readonly();

export type LiveBoardRow = z.infer<typeof LiveBoardRowSchema>;
export type AdaptedBoardRow = {
  readonly artifactSha256: string;
  readonly axes: z.infer<typeof AXES>;
  readonly communityModelGroupId: string | undefined;
  readonly compositeFull: number | null;
  readonly declaredBaseModels: readonly string[];
  readonly displayName: string;
  readonly family: string | null;
  readonly globalRank: number | null;
  readonly headlineComplete: boolean;
  readonly indexVersion: string | null;
  readonly lineageEnrichment: Readonly<Record<string, unknown>> | undefined;
  readonly origin: "community" | "project_anchor";
  readonly quantLabel: string | null;
  readonly submissionId: string;
  readonly submitterDisplayName: string | null;
  readonly submitterGithubLogin: string | null;
  readonly submitterKeyFingerprint: string | null;
  readonly timestamps: z.infer<typeof TIMESTAMPS> | null;
  readonly trust: Readonly<Record<string, unknown>> | null;
};

export type ParsedBoardEnvelope = {
  readonly droppedRows: number;
  readonly edgeBlockRevision: number;
  readonly generatedAt: string;
  readonly publicationRevision: number;
  readonly rows: readonly AdaptedBoardRow[];
};

export function parseBoardEnvelope(value: unknown): ParsedBoardEnvelope | null {
  const envelope = LiveBoardEnvelopeSchema.safeParse(value);
  if (!envelope.success) return null;
  const rows: AdaptedBoardRow[] = [];
  let droppedRows = envelope.data.omitted_rows;
  for (const candidate of envelope.data.rows) {
    const parsed = UnifiedBoardRowSchema.safeParse(candidate);
    if (parsed.success) rows.push(adaptRow(parsed.data));
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

export function adaptLegacyBoardRow(value: LiveBoardRow): AdaptedBoardRow {
  return adaptRow(UnifiedBoardRowSchema.parse(value));
}

export function publicProtocolLabel(indexVersion: string | null | undefined): string {
  return indexVersion === "index-v4.1" ? "LB-2026-07" : indexVersion ?? "protocol unavailable";
}

function adaptRow(row: z.infer<typeof UnifiedBoardRowSchema>): AdaptedBoardRow {
  return {
    artifactSha256: row.model.file_sha256,
    axes: row.axes,
    communityModelGroupId: row.community_model_group_id,
    compositeFull: row.scores.composite_full ?? row.scores.headline_score ?? row.scores.composite ?? null,
    declaredBaseModels: row.lineage?.base_model ?? [],
    displayName: row.model.display_name ?? row.model.declared_name ?? "Reported model",
    family: row.model.family ?? null,
    globalRank: row.global_rank ?? row.rank ?? null,
    headlineComplete: row.headline_complete,
    indexVersion: row.index_version ?? null,
    lineageEnrichment: row.lineage_enrichment,
    origin: row.origin,
    quantLabel: row.model.quant_label ?? null,
    submissionId: row.submission_id,
    submitterDisplayName: row.submitter.display_name ?? null,
    submitterGithubLogin: row.submitter.github_login ?? null,
    submitterKeyFingerprint: row.submitter.key_fingerprint ?? null,
    timestamps: row.timestamps ?? null,
    trust: row.trust ?? null,
  };
}

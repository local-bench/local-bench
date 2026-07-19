import { z } from "zod";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
function safeText(maxCodePoints: number) {
  return z.string().refine((value) => [...value].length <= maxCodePoints, `must contain at most ${maxCodePoints} code points`)
    .refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}
const SAFE_TEXT = safeText(300);
const SCORE = z.number().finite().min(0).max(100);
const TIMESTAMP = z.string().refine((value) => !Number.isNaN(Date.parse(value)));
const SHA256 = z.string().regex(/^[0-9a-f]{64}$/u);
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
  unverified_handle: safeText(80).nullable().optional(),
}).passthrough().readonly();
const TIMESTAMPS = z.object({
  published_at: TIMESTAMP,
  submitted_at: TIMESTAMP,
  validated_at: TIMESTAMP.optional(),
}).passthrough().readonly();
const LINEAGE = z.object({
  base_model: z.array(SAFE_TEXT).max(8).readonly().default([]),
}).passthrough().readonly();
const LINEAGE_ENRICHMENT = z.object({
  artifact_sha256: SHA256,
  association: z.object({
    artifact_to_repo: z.literal("unverified"),
    basis: z.literal("maintainer-associated"),
    note: SAFE_TEXT,
  }).passthrough().readonly(),
  card_declared_edges: z.array(z.object({
    base: SAFE_TEXT,
    base_revision: z.string().regex(/^[0-9a-f]{40}$/u).nullable(),
    child: SAFE_TEXT,
    child_revision: z.string().regex(/^[0-9a-f]{40}$/u),
    source: z.enum(["hf-model-card", "maintainer-asserted"]),
  }).passthrough().readonly()).readonly(),
  repo: z.object({
    id: SAFE_TEXT,
    revision: z.string().regex(/^[0-9a-f]{40}$/u),
  }).passthrough().readonly(),
  resolution: z.object({
    resolved_at: TIMESTAMP,
    status: z.enum(["complete", "truncated", "partial"]),
  }).passthrough().readonly(),
}).passthrough().readonly();

export const LiveBoardRowSchema = z.object({
  axes: AXES,
  badge: z.literal("project-run").optional(),
  community_model_group_id: SAFE_TEXT,
  conformance: z.record(z.string(), z.unknown()).default({}),
  coverage_profile_id: SAFE_TEXT,
  group_path: SAFE_TEXT,
  headline_complete: z.boolean(),
  index_version: SAFE_TEXT.nullable(),
  lineage: LINEAGE,
  lineage_enrichment: LINEAGE_ENRICHMENT.optional(),
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
  badge: z.literal("project-run").optional(),
  community_model_group_id: SAFE_TEXT.optional(),
  global_rank: z.number().int().positive().nullable().optional(),
  headline_complete: z.boolean(),
  index_version: SAFE_TEXT.nullable().optional(),
  lineage: LINEAGE.optional(),
  lineage_enrichment: LINEAGE_ENRICHMENT.optional(),
  model: MODEL,
  origin: z.enum(["community", "project_anchor"]),
  rank: z.number().int().positive().nullable().optional(),
  ranked: z.boolean().optional(),
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
  readonly badge?: "project-run";
  readonly communityModelGroupId: string | undefined;
  readonly compositeFull: number | null;
  readonly declaredBaseModels: readonly string[];
  readonly displayName: string;
  readonly family: string | null;
  readonly globalRank: number | null;
  readonly headlineComplete: boolean;
  readonly indexVersion: string | null;
  readonly lineageEnrichment: z.infer<typeof LINEAGE_ENRICHMENT> | undefined;
  readonly origin: "community" | "project_anchor";
  readonly quantLabel: string | null;
  readonly ranked: boolean;
  readonly submissionId: string;
  readonly submitterDisplayName: string | null;
  readonly submitterGithubLogin: string | null;
  readonly submitterKeyFingerprint: string | null;
  readonly timestamps: z.infer<typeof TIMESTAMPS> | null;
  readonly trust?: Readonly<Record<string, unknown>>;
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
    axes: normalizeAxes(row.axes),
    ...(row.badge === undefined ? {} : { badge: row.badge }),
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
    ranked: row.ranked ?? row.headline_complete,
    submissionId: row.submission_id,
    submitterDisplayName: row.submitter.display_name ?? row.submitter.unverified_handle ?? null,
    submitterGithubLogin: row.submitter.github_login ?? null,
    submitterKeyFingerprint: row.submitter.key_fingerprint ?? null,
    timestamps: row.timestamps ?? null,
    ...(row.trust === undefined ? {} : { trust: row.trust }),
  };
}

const LEGACY_AXIS_NAMES: Readonly<Record<string, string>> = {
  call_formatting: "tool_calling",
  instruction: "instruction_following",
  tool_use: "agentic",
};

export function canonicalBoardAxisName(axis: string): string {
  return LEGACY_AXIS_NAMES[axis] ?? axis;
}

export function boardAxisValue<T>(axes: Readonly<Record<string, T>>, axis: string): T | undefined {
  const canonical = canonicalBoardAxisName(axis);
  const canonicalValue = axes[canonical];
  if (canonicalValue !== undefined) return canonicalValue;
  for (const [legacy, canonicalName] of Object.entries(LEGACY_AXIS_NAMES)) {
    if (canonicalName !== canonical) continue;
    const legacyValue = axes[legacy];
    if (legacyValue !== undefined) return legacyValue;
  }
  return undefined;
}

function normalizeAxes(axes: z.infer<typeof AXES>): z.infer<typeof AXES> {
  const normalized = { ...axes };
  for (const [legacy, canonical] of Object.entries(LEGACY_AXIS_NAMES)) {
    const legacyAxis = normalized[legacy];
    if (legacyAxis !== undefined && normalized[canonical] === undefined) {
      normalized[canonical] = legacyAxis;
    }
    delete normalized[legacy];
  }
  return normalized;
}

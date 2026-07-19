import { z } from "zod";

const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const GROUP_ID_RE = /^community-group:[0-9a-f]{32}$/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;
const REVISION_RE = /^[0-9a-f]{40}$/u;
const SUBMISSION_ID_RE = /^ticket_[0-9a-f]{32}$/u;
const FINGERPRINT_RE = /^[0-9a-f]{12}$/u;
// GitHub login grammar (1-39 chars, alphanumeric with interior hyphens) enforced
// exactly at the public boundary so a verified-looking handle can never be a
// 40-char or hyphen-edged spoof.
const GITHUB_LOGIN_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/u;
const ISO_8601_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u;

function safeText(maxCodePoints: number, minCodePoints = 0) {
  return z.string().refine(
    (value) => [...value].length >= minCodePoints && [...value].length <= maxCodePoints,
    `must contain ${minCodePoints}-${maxCodePoints} code points`,
  ).refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}

const ScoreSchema = z.number().finite().min(0).max(1);
const Sha256Schema = z.string().regex(SHA256_RE);
const RevisionSchema = z.string().regex(REVISION_RE);
const TimestampSchema = z.string().regex(ISO_8601_RE).refine((value) => !Number.isNaN(Date.parse(value)));
const IdSchema = safeText(140, 1);
const AxisKeySchema = safeText(40, 1);
const RepoIdSchema = safeText(140, 1);
const HfRepoSchema = safeText(140, 3).regex(/^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/u);
const HfFilenameSchema = safeText(240, 1).refine(
  (value) => !value.startsWith("/") && !value.includes("\\") && !value.includes("://") && !value.split("/").includes(".."),
);

const ScoresSchema = z.object({
  composite_full: ScoreSchema.nullable().optional(),
  composite_static: ScoreSchema.nullable().optional(),
  headline_score: ScoreSchema.nullable(),
  known_headline_contribution: ScoreSchema,
  measured_headline_weight: ScoreSchema,
  missing_headline_weight: ScoreSchema,
  n: z.number().int().nonnegative().optional(),
  partial_composite: ScoreSchema,
  partial_composite_scope: z.literal("measured_headline_axes"),
  rank_scope: safeText(120, 1),
  static_index_version: safeText(120, 1).optional(),
}).strict().readonly();

const AxisSchema = z.object({
  ci: z.tuple([ScoreSchema, ScoreSchema]).nullable(),
  n: z.number().int().nonnegative().max(10_000_000),
  score: ScoreSchema.nullable(),
  status: z.enum(["measured", "not_measured", "invalid"]),
}).strict().readonly();

const AxesSchema = z.record(AxisKeySchema, AxisSchema).superRefine((axes, context) => {
  if (Object.keys(axes).length > 16) {
    context.addIssue({ code: "custom", message: "axes must contain at most 16 entries" });
  }
}).readonly();

const LineageEnrichmentSchema = z.object({
  artifact_sha256: Sha256Schema,
  association: z.object({
    artifact_to_repo: z.literal("unverified"),
    basis: z.literal("maintainer-associated"),
    note: safeText(300),
  }).strict().readonly(),
  card_declared_edges: z.array(z.object({
    base: RepoIdSchema,
    base_revision: RevisionSchema.nullable(),
    child: RepoIdSchema,
    child_revision: RevisionSchema,
    source: z.enum(["hf-model-card", "maintainer-asserted"]),
  }).strict().readonly()).max(8).readonly(),
  repo: z.object({ id: RepoIdSchema, revision: RevisionSchema }).strict().readonly(),
  resolution: z.object({
    resolved_at: TimestampSchema,
    status: z.enum(["complete", "truncated", "partial"]),
  }).strict().readonly(),
}).strict().readonly();

function safeJson(value: unknown): boolean {
  if (typeof value === "string") return !UNSAFE_TEXT_RE.test(value);
  if (Array.isArray(value)) return value.every(safeJson);
  if (typeof value !== "object" || value === null) return true;
  return Object.entries(value).every(([key, child]) => !UNSAFE_TEXT_RE.test(key) && safeJson(child));
}

const SafeJsonSchema = z.json().refine(safeJson, "contains unsafe text characters");
const ConformanceSchema = z.object({
  n_scored: z.number().int().nonnegative().optional(),
  per_bench: z.record(AxisKeySchema, SafeJsonSchema).optional(),
  reasons: z.array(safeText(300)).max(24).readonly().optional(),
  status: safeText(32, 1).optional(),
  worst_bench: safeText(120, 1).nullable().optional(),
}).strict().readonly();

const RescoreModesSchema = z.object({
  amo: z.enum(["rescored", "verdict_carried"]).optional(),
  appworld_c: z.enum(["rescored", "verdict_carried"]).optional(),
  bfcl: z.enum(["rescored", "verdict_carried"]).optional(),
  bfcl_multi_turn_base: z.enum(["rescored", "verdict_carried"]).optional(),
  bfcl_multi_turn_long_context: z.enum(["rescored", "verdict_carried"]).optional(),
  bigcodebench_hard: z.enum(["rescored", "verdict_carried"]).optional(),
  ifbench: z.enum(["rescored", "verdict_carried"]).optional(),
  lcb: z.enum(["rescored", "verdict_carried"]).optional(),
  mmlu_pro: z.enum(["rescored", "verdict_carried"]).optional(),
  olymmath_hard: z.enum(["rescored", "verdict_carried"]).optional(),
  tc_json_v1: z.enum(["rescored", "verdict_carried"]).optional(),
}).strict().readonly();

const OriginChipSchema = z.enum(["maintainer-run", "self-reported"]);
const LegacyLiveTrustSchema = z.object({
  agentic_provenance: safeText(32, 1),
  chip: OriginChipSchema.optional(),
  coding_state: safeText(32, 1),
  replicated: z.boolean(),
  tier: safeText(32, 1),
  trust_label: safeText(32, 1),
  verification_level: safeText(32, 1),
}).strict();
const OriginChipTrustSchema = z.object({ chip: OriginChipSchema }).strict();
type NormalizedLiveTrust = {
  readonly agentic_provenance: string;
  readonly chip?: "maintainer-run" | "self-reported";
  readonly coding_state: string;
  readonly replicated: boolean;
  readonly tier: string;
  readonly trust_label: string;
  readonly verification_level: string;
};
const LiveTrustSchema = z.union([OriginChipTrustSchema, LegacyLiveTrustSchema]).transform((trust): NormalizedLiveTrust => {
  if ("agentic_provenance" in trust) {
    return {
      ...trust,
      chip: trust.chip ?? (trust.trust_label === "project_anchor" ? "maintainer-run" : "self-reported"),
    };
  }
  return {
    agentic_provenance: trust.chip === "maintainer-run" ? "attested" : "self-reported",
    chip: trust.chip,
    coding_state: "client-reported",
    replicated: false,
    tier: trust.chip,
    trust_label: trust.chip === "maintainer-run" ? "project_anchor" : "community_self_submitted",
    verification_level: "client_reported",
  };
});

export const LiveBoardRowSchema = z.object({
  axes: AxesSchema,
  badge: z.literal("project-run").optional(),
  community_model_group_id: z.string().regex(GROUP_ID_RE).optional(),
  conformance: ConformanceSchema,
  coverage_profile_id: IdSchema,
  group_path: safeText(140, 1).optional(),
  headline_complete: z.boolean(),
  index_version: safeText(32, 1).nullable(),
  lineage: z.object({ base_model: z.array(RepoIdSchema).max(8).readonly() }).strict().readonly(),
  lineage_enrichment: LineageEnrichmentSchema.optional(),
  model: z.object({
    declared_name: safeText(120).nullable(),
    display_name: safeText(120).nullable(),
    family: safeText(64).nullable(),
    file_sha256: Sha256Schema,
    hf: z.object({ filename: HfFilenameSchema, repo: HfRepoSchema, revision: RevisionSchema }).strict().readonly().optional(),
    identity_status: z.enum(["unverified", "maintainer_verified"]).optional(),
    model_system_key: z.string().regex(/^artifact:[0-9a-f]{64}$/u),
    quant_label: safeText(32).nullable(),
  }).strict().readonly(),
  origin: z.enum(["community", "project_anchor"]),
  normalization_annotations: z.array(z.object({
    client_values: z.object({
      composite_full: ScoreSchema.nullable(),
      headline_score: ScoreSchema.nullable(),
      partial_composite: ScoreSchema,
    }).strict().readonly(),
    code: z.literal("client_composite_drift"),
    fields: z.array(z.enum(["headline_score", "partial_composite", "composite_full"])).min(1).max(3).readonly(),
    server_value: ScoreSchema,
  }).strict().readonly()).max(1).readonly().optional(),
  provenance_notes: z.array(safeText(300)).max(16).readonly().optional(),
  ranked: z.boolean().optional(),
  receipt_references: z.object({ coding_receipt_sha256: Sha256Schema.nullable() }).strict().readonly(),
  rescore_modes: RescoreModesSchema,
  scorecard_id: IdSchema,
  scores: ScoresSchema,
  submission_id: z.string().regex(SUBMISSION_ID_RE),
  submitter: z.object({
    display_name: safeText(80).nullable().optional(),
    github_login: z.string().regex(GITHUB_LOGIN_RE).nullable().optional(),
    key_fingerprint: z.string().regex(FINGERPRINT_RE).nullable(),
    unverified_handle: safeText(80).nullable().optional(),
  }).strict().readonly(),
  suite_release_id: IdSchema,
  timestamps: z.object({
    published_at: TimestampSchema,
    submitted_at: TimestampSchema,
    validated_at: TimestampSchema,
  }).strict().readonly(),
  trust: LiveTrustSchema.optional(),
}).strict().readonly().superRefine((row, context) => {
  if (row.trust === undefined) {
    if (row.origin === "project_anchor" && row.badge !== "project-run") {
      context.addIssue({ code: "custom", message: "project rows require the project-run badge" });
    }
    if (row.origin === "community" && row.badge !== undefined) {
      context.addIssue({ code: "custom", message: "community rows must remain unmarked" });
    }
  } else {
    const expectedChip = row.origin === "project_anchor" ? "maintainer-run" : "self-reported";
    if (row.trust.chip !== expectedChip) {
      context.addIssue({ code: "custom", message: "legacy trust chip must be derived from origin" });
    }
  }
  if (row.origin === "community" && (row.community_model_group_id === undefined || row.group_path === undefined)) {
    context.addIssue({ code: "custom", message: "community rows require a model group" });
  }
  if (row.community_model_group_id !== undefined && row.group_path !== `community/groups/${row.community_model_group_id.replace("community-group:", "")}.json`) {
    context.addIssue({ code: "custom", message: "group_path must match community_model_group_id" });
  }
});

export const LiveBoardEnvelopeSchema = z.object({
  board_digest: Sha256Schema,
  edge_block_revision: z.number().int().nonnegative(),
  generated_at: TimestampSchema,
  omitted_rows: z.number().int().nonnegative().optional().default(0),
  publication_revision: z.number().int().nonnegative(),
  rows: z.array(z.unknown()).max(500).readonly(),
  schema_version: z.literal("localbench.community_live_board.v1"),
}).strict().readonly();

export type LiveBoardRow = z.infer<typeof LiveBoardRowSchema>;

import { z } from "zod";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export type JsonRecord = { readonly [key: string]: JsonValue };

export type ProjectionAxis = {
  readonly [key: string]: JsonValue | undefined;
  readonly n?: number;
};

export type AcceptedResultProjectionV1 = {
  readonly artifact_hashes: {
    readonly bundle_sha256: string;
    readonly projection_sha256: string;
    readonly public_artifact_manifest_sha256?: string | null;
  };
  readonly axes: Record<string, ProjectionAxis>;
  readonly benches?: JsonRecord;
  readonly conformance: JsonRecord;
  readonly coverage_profile_id: string;
  readonly headline_complete: boolean;
  readonly lane_id?: string | null;
  readonly model: {
    readonly display_name?: string | null;
    readonly family?: string | null;
    readonly file_sha256?: string | null;
    readonly quant_label?: string | null;
  };
  readonly n_errors?: number;
  readonly origin: "project_anchor" | "community_submission";
  readonly runtime: {
    readonly hardware_summary?: string | null;
    readonly name?: string | null;
    readonly version?: string | null;
  };
  readonly schema_version: string;
  readonly scorecard_id: string;
  readonly scores: {
    readonly headline_score?: number | null;
    readonly known_headline_contribution: number;
    readonly measured_headline_weight: number;
    readonly missing_headline_weight: number;
    readonly partial_composite?: number | null;
    readonly rank_scope: string;
  };
  readonly suite_manifest_sha256: string;
  readonly suite_release_id: string;
  readonly tier?: string | null;
  readonly trust_label: string;
  readonly validator?: JsonRecord;
  readonly verification_level: string;
  readonly warnings?: readonly string[];
};

export type BoardEntryIdentity = {
  readonly entryId: string;
  readonly publishedAt: string | null;
  readonly scopeRank?: number | null;
  readonly submissionId: string;
  readonly visibility: "private" | "preview" | "public";
};

export type BoardEntryRow = {
  readonly entry_id: string;
  readonly submission_id: string;
  readonly board_schema_version: "localbench.board_entries.v1";
  readonly published_at: string | null;
  readonly visibility: "private" | "preview" | "public";
  readonly origin: "project_anchor" | "community_submission";
  readonly trust_label: string;
  readonly verification_level: string;
  readonly model_display_name: string | null;
  readonly model_family: string | null;
  readonly model_file_sha256: string | null;
  readonly model_quant_label: string | null;
  readonly runtime_name: string | null;
  readonly runtime_version: string | null;
  readonly hardware_summary: string | null;
  readonly lane_id: string | null;
  readonly tier: string | null;
  readonly suite_release_id: string;
  readonly suite_manifest_sha256: string;
  readonly scorecard_id: string;
  readonly coverage_profile_id: string;
  readonly headline_complete: 0 | 1;
  readonly headline_score: number | null;
  readonly partial_composite: number | null;
  readonly measured_headline_weight: number;
  readonly missing_headline_weight: number;
  readonly known_headline_contribution: number;
  readonly rank_scope: string;
  readonly global_rank: number | null;
  readonly scope_rank: number | null;
  readonly axis_scores_json: string;
  readonly bench_scores_json: string;
  readonly conformance_json: string;
  readonly n_scored: number;
  readonly n_errors: number;
  readonly warning_count: number;
  readonly projection_sha256: string;
  readonly bundle_sha256: string;
  readonly public_artifact_manifest_sha256: string | null;
};

export function acceptedProjectionToBoardEntry(
  projection: AcceptedResultProjectionV1,
  identity: BoardEntryIdentity,
): BoardEntryRow {
  return {
    axis_scores_json: JSON.stringify(projection.axes),
    bench_scores_json: JSON.stringify(projection.benches ?? {}),
    board_schema_version: "localbench.board_entries.v1",
    bundle_sha256: projection.artifact_hashes.bundle_sha256,
    conformance_json: JSON.stringify(projection.conformance),
    coverage_profile_id: projection.coverage_profile_id,
    entry_id: identity.entryId,
    global_rank: null,
    hardware_summary: projection.runtime.hardware_summary ?? null,
    headline_complete: projection.headline_complete ? 1 : 0,
    headline_score: projection.scores.headline_score ?? null,
    known_headline_contribution: projection.scores.known_headline_contribution,
    lane_id: projection.lane_id ?? null,
    measured_headline_weight: projection.scores.measured_headline_weight,
    missing_headline_weight: projection.scores.missing_headline_weight,
    model_display_name: projection.model.display_name ?? null,
    model_family: projection.model.family ?? null,
    model_file_sha256: projection.model.file_sha256 ?? null,
    model_quant_label: projection.model.quant_label ?? null,
    n_errors: projection.n_errors ?? sumBenchErrors(projection.benches),
    n_scored: sumAxisCounts(projection.axes),
    origin: projection.origin,
    partial_composite: projection.scores.partial_composite ?? null,
    projection_sha256: projection.artifact_hashes.projection_sha256,
    public_artifact_manifest_sha256: projection.artifact_hashes.public_artifact_manifest_sha256 ?? null,
    published_at: identity.publishedAt,
    rank_scope: projection.scores.rank_scope,
    runtime_name: projection.runtime.name ?? null,
    runtime_version: projection.runtime.version ?? null,
    scope_rank: identity.scopeRank ?? null,
    scorecard_id: projection.scorecard_id,
    submission_id: identity.submissionId,
    suite_manifest_sha256: projection.suite_manifest_sha256,
    suite_release_id: projection.suite_release_id,
    tier: projection.tier ?? null,
    trust_label: projection.trust_label,
    verification_level: projection.verification_level,
    visibility: identity.visibility,
    warning_count: projection.warnings?.length ?? 0,
  };
}

function sumAxisCounts(axes: Record<string, ProjectionAxis>): number {
  return Object.values(axes).reduce<number>((total, axis) => total + (axis.n ?? 0), 0);
}

function sumBenchErrors(benches: JsonRecord | undefined): number {
  if (benches === undefined) {
    return 0;
  }
  return Object.values(benches).reduce<number>((total, bench) => {
    if (!isJsonRecord(bench)) {
      return total;
    }
    const value = bench["n_errors"];
    return total + (typeof value === "number" ? value : 0);
  }, 0);
}

function isJsonRecord(value: JsonValue): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// --- Validation for loading PUBLISHED partial-coverage projections from public/data ---
// Partial-coverage rows are published submissions that measured only a subset of headline axes
// (e.g. the 4-axis text+code profile, missing agentic). They are deliberately UNRANKED. The site
// reads an accepted_result_projection_v1 per published submission and maps it through the same
// acceptedProjectionToBoardEntry() used by the D1 index, so the board row matches the index row.

const ProjectionAxisSchema = z.object({ n: z.number().optional() }).passthrough();
const JsonObjectSchema = z.record(z.string(), z.unknown());

export const AcceptedResultProjectionSchema = z.object({
  artifact_hashes: z.object({
    bundle_sha256: z.string(),
    projection_sha256: z.string(),
    public_artifact_manifest_sha256: z.string().nullable().optional(),
  }),
  axes: z.record(z.string(), ProjectionAxisSchema),
  benches: JsonObjectSchema.optional(),
  conformance: JsonObjectSchema,
  coverage_profile_id: z.string(),
  headline_complete: z.boolean(),
  lane_id: z.string().nullable().optional(),
  model: z.object({
    display_name: z.string().nullable().optional(),
    family: z.string().nullable().optional(),
    file_sha256: z.string().nullable().optional(),
    quant_label: z.string().nullable().optional(),
  }),
  n_errors: z.number().optional(),
  origin: z.enum(["project_anchor", "community_submission"]),
  runtime: z.object({
    hardware_summary: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    version: z.string().nullable().optional(),
  }),
  schema_version: z.string(),
  scorecard_id: z.string(),
  scores: z.object({
    headline_score: z.number().nullable().optional(),
    known_headline_contribution: z.number(),
    measured_headline_weight: z.number(),
    missing_headline_weight: z.number(),
    partial_composite: z.number().nullable().optional(),
    rank_scope: z.string(),
  }),
  suite_manifest_sha256: z.string(),
  suite_release_id: z.string(),
  tier: z.string().nullable().optional(),
  trust_label: z.string(),
  validator: JsonObjectSchema.optional(),
  verification_level: z.string(),
  warnings: z.array(z.string()).optional(),
});

export const BoardEntryIdentitySchema = z.object({
  entryId: z.string(),
  publishedAt: z.string().nullable(),
  scopeRank: z.number().nullable().default(null),
  submissionId: z.string(),
  visibility: z.enum(["private", "preview", "public"]),
});

export const PartialCoverageDataSchema = z.object({
  generated_note: z.string().optional(),
  entries: z.array(
    z.object({
      identity: BoardEntryIdentitySchema,
      projection: AcceptedResultProjectionSchema,
    }),
  ),
});

export type PartialCoverageData = z.infer<typeof PartialCoverageDataSchema>;

// Map a validated partial-coverage file into board rows via the same projection->row mapper the
// D1 index uses. Casts the Zod-parsed projection to the hand-written type (records widen to
// unknown under Zod); the mapper only reads well-typed scalar fields + JSON.stringifies the records.
export function partialCoverageRows(data: PartialCoverageData): readonly BoardEntryRow[] {
  return data.entries.map((entry) =>
    acceptedProjectionToBoardEntry(entry.projection as unknown as AcceptedResultProjectionV1, entry.identity),
  );
}

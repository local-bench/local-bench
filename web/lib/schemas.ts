import { z } from "zod";

export const ModelSlugSchema = z.string().min(1).brand<"ModelSlug">();
export const RunIdSchema = z.string().min(1).brand<"RunId">();

const JsonPrimitiveSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const PrimitiveRecordSchema = z.record(z.string(), JsonPrimitiveSchema);
const FullShaSchema = z.string().regex(/^[0-9a-fA-F]{40}$/);
const FullSha256Schema = z.string().regex(/^[0-9a-fA-F]{64}$/);

export const RuntimeNameSchema = z.enum(["llama.cpp", "vllm"]);

export const ScoreSchema = z
  .object({
    point: z.number(),
    lo: z.number(),
    hi: z.number(),
    point_raw: z.number().optional(),
    lo_raw: z.number().optional(),
    hi_raw: z.number().optional(),
  })
  .passthrough();

export const AxisScoreSchema = ScoreSchema.extend({
  raw_accuracy: z.number(),
  n: z.number(),
  n_errors: z.number(),
  n_no_answer: z.number(),
  n_unscoreable: z.number().optional(),
  // IFBench strict decomposition (present once strict-scored run JSONs are wired; flat per the
  // producer's shape — see docs/SITE-DATA-CONTRACT.md). raw_accuracy above IS the strict accuracy.
  termination_rate: z.number().optional(),
  conditional_accuracy: z.number().optional(),
});

export const AxesSchema = z.record(z.string(), AxisScoreSchema);
export const AxisStatusSchema = z.record(
  z.string(),
  z
    .object({
      axis: z.string(),
      status: z.enum(["measured", "not_measured", "generated_unverified"]),
      reason: z.string(),
      detail: z.string().optional(),
    })
    .passthrough(),
);
export const ConformanceGateSchema = z.object({
  id: z.literal("tc_json_v1"),
  label: z.literal("Tool-calling"),
  band: z.enum(["green", "amber", "red"]),
  pass_rate: z.object({
    point: z.number(),
    lo: z.number(),
    hi: z.number(),
  }),
  invalid_json_rate: z.number(),
  n_items: z.number(),
  threshold_version: z.literal("tc_json_v1"),
  band_reasons: z.array(z.string()),
});
export const ConformanceGatesSchema = z
  .object({
    tc_json_v1: ConformanceGateSchema.optional(),
  })
  .passthrough();

export const ScorecardSummarySchema = z.object({
  current_id: z.string().nullable().optional(),
  current_registry_digest: z.string().nullable().optional(),
  drift: z.boolean(),
  execution_profile_id: z.string().nullable().optional(),
  id: z.string().nullable(),
  registry_digest: z.string().nullable().optional(),
  registry_drift: z.boolean().optional(),
  version: z.string().nullable(),
});

export const KindSchema = z.enum(["anchor", "community"]);
export const ScoreStatusSchema = z.enum(["measured", "missing"]);
export const BoardOriginSchema = z.enum(["project_anchor", "community", "community_submission"]);
export const AgenticProvenanceSchema = z.enum(["none", "project_attested", "self_reported"]);
export const ModelKindSchema = z.enum(["base", "finetune", "distill", "merge"]);
const DemoFlagSchema = z.boolean().optional().default(false);

export const GpuSchema = z.object({
  name: z.string().nullable(),
  vram_gb: z.number().nullable(),
  vram_mb: z.number().nullable(),
  driver: z.string().nullable(),
});

export const HardwareSchema = z.object({
  gpu: GpuSchema.nullable(),
  cpu: z.string().nullable(),
  ram_gb: z.number().nullable(),
  os: z.string().nullable(),
});

export const RuntimeSchema = z.object({
  name: RuntimeNameSchema.nullable(),
  version: z.string().nullable(),
  kv_cache_quant: z.string().nullable(),
  ctx_len_configured: z.number().nullable(),
  parallel_slots: z.number().nullable(),
});
const IndexRuntimeSchema = RuntimeSchema.partial();

const SamplingBenchSchema = z
  .object({
    max_tokens: z.number().nullable(),
    temperature: z.number().nullable(),
  })
  .passthrough();

export const SamplingSchema = z
  .object({
    by_bench: z.record(z.string(), SamplingBenchSchema),
    min_p: z.number().nullable().optional(),
    reasoning_effort: z.string().nullable().optional(),
    seed: z.number().nullable().optional(),
    temperature: z.number().nullable(),
    thinking_mode: z.string().nullable(),
    top_k: z.number().nullable().optional(),
    top_p: z.number().nullable().optional(),
  })
  .passthrough();

export const TotalsSchema = z.object({
  n_items: z.number(),
  n_errors: z.number(),
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  total_tokens: z.number(),
  wall_time_seconds: z.number(),
  completion_tokens_per_second: z.number().nullable(),
});

const PerfBenchSchema = z
  .object({
    prefill_tps: z.number().nullable(),
    decode_tps: z.number().nullable(),
    prompt_ms_median: z.number().nullable(),
    n: z.number(),
  })
  .passthrough();

export const PerfSchema = z
  .object({
    // cli/src/localbench/perf.py emits llama.cpp when server timings exist, else null.
    timings_source: z.literal("llama.cpp").nullable(),
    timings_coverage: z.number(),
    prefill_tps: z.number().nullable(),
    decode_tps: z.number().nullable(),
    prompt_ms_median: z.number().nullable(),
    prompt_ms_p95: z.number().nullable(),
    predicted_ms_median: z.number().nullable(),
    predicted_ms_p95: z.number().nullable(),
    ttft_proxy_ms_median: z.number().nullable(),
    per_bench: z.record(z.string(), PerfBenchSchema),
  })
  .passthrough();

const SnapshotFileSchema = z.object({
  path: z.string().min(1),
  sha256: FullSha256Schema,
  size_bytes: z.number().int().nonnegative(),
});

export const ServingProvenanceSchema = z.object({
  runtime: RuntimeNameSchema,
  engine_version: z.string().nullable(),
  engine_executable_sha256: FullSha256Schema.nullable(),
  dependency_lock_sha256: FullSha256Schema.nullable(),
  runtime_identity_sha256: FullSha256Schema.nullable(),
  snapshot: z
    .object({
      repo: z.string().min(1),
      revision: FullShaSchema,
      merkle_sha256: FullSha256Schema,
      files: z.array(SnapshotFileSchema).min(1),
    })
    .nullable(),
  determinism: z.object({
    engine_log_evidence: z.array(z.string()),
    engine_log_semantic_verdict: z.boolean(),
    two_start_canary_passed: z.boolean(),
  }),
  numerics: z.object({
    dtype: z.string().nullable(),
    kv_cache_quant: z.string().nullable(),
    mamba_ssm_cache_dtype: z.string().nullable(),
    model_config_mamba_ssm_dtype: z.string().nullable(),
    quantization: z.string().nullable(),
  }),
});

type RuntimeBearingRow = {
  readonly runtime?: { readonly name?: "llama.cpp" | "vllm" | null | undefined } | undefined;
  readonly serving_provenance?: z.infer<typeof ServingProvenanceSchema> | undefined;
};

function requireValidVllmProvenance(row: RuntimeBearingRow, ctx: z.RefinementCtx): void {
  const manifestRuntime = row.runtime?.name;
  const provenance = row.serving_provenance;
  if (manifestRuntime !== "vllm" && provenance?.runtime !== "vllm") return;
  if (manifestRuntime !== "vllm") {
    ctx.addIssue({ code: "custom", message: "vLLM provenance requires manifest runtime vllm", path: ["runtime", "name"] });
  }
  if (provenance === undefined) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires serving provenance", path: ["serving_provenance"] });
    return;
  }
  if (provenance.runtime !== manifestRuntime) {
    ctx.addIssue({ code: "custom", message: "manifest and provenance runtimes must match", path: ["serving_provenance", "runtime"] });
  }
  if (provenance.snapshot === null) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires immutable snapshot identity", path: ["serving_provenance", "snapshot"] });
  }
  if (provenance.engine_version === null) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires engine version identity", path: ["serving_provenance", "engine_version"] });
  }
  if (provenance.engine_executable_sha256 === null) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires engine executable identity", path: ["serving_provenance", "engine_executable_sha256"] });
  }
  if (provenance.dependency_lock_sha256 === null) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires dependency lock identity", path: ["serving_provenance", "dependency_lock_sha256"] });
  }
  if (provenance.runtime_identity_sha256 === null) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires runtime identity", path: ["serving_provenance", "runtime_identity_sha256"] });
  }
  if (provenance.determinism.engine_log_evidence.length === 0 || !provenance.determinism.engine_log_semantic_verdict || !provenance.determinism.two_start_canary_passed) {
    ctx.addIssue({ code: "custom", message: "vLLM runtime requires successful determinism evidence", path: ["serving_provenance", "determinism"] });
  }
}

export const IndexModelSchema = z.object({
  slug: ModelSlugSchema,
  catalog_id: z.string().nullable().optional(),
  model_label: z.string(),
  family: z.string(),
  kind: KindSchema,
  best_run_id: RunIdSchema.nullable(),
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  composite_full: ScoreSchema.nullable().optional(),
  composite_static: ScoreSchema.nullable().optional(),
  conformance_status: z.string().nullable().optional(),
  axes: AxesSchema,
  axis_status: AxisStatusSchema.optional(),
  tier: z.string().nullable(),
  lane: z.string().nullable(),
  n_runs: z.number(),
  ranked: z.boolean(),
  tokens_to_answer_median: z.number().nullable(),
  tokens_to_answer_p95: z.number().nullable().optional(),
  est_cost_usd: z.number().nullable(),
  latency_s_median: z.number().nullable().optional(),
  wall_time_seconds: z.number().nullable().optional(),
  // GPU that produced the best run (lifted onto the board row from the run hardware). null for
  // catalog shells / API anchors. Only the compact name + VRAM are shown in the Hardware column.
  gpu: GpuSchema.nullable().optional(),
  runtime: IndexRuntimeSchema.optional(),
  serving_provenance: ServingProvenanceSchema.optional(),
  // V2 stub: who submitted the top run (community submissions). Absent in v1 (maintainer-only,
  // anonymous), so the User column renders a neutral placeholder.
  submitted_by: z.string().nullable().optional(),
  submitter_display_name: z.string().nullable().optional(),
  origin: BoardOriginSchema.optional(),
  trust_label: z.string().optional(),
  agentic_provenance: AgenticProvenanceSchema.optional(),
  provenance_notes: z.array(z.string()).optional(),
  static_index_version: z.string().optional(),
  replicated: z.boolean(),
  score_status: ScoreStatusSchema.optional().default("measured"),
  has_code_artifacts: z.boolean().optional(),
  verdict_source: z.string().nullable().optional(),
  conformance_gates: ConformanceGatesSchema.optional(),
  demo: DemoFlagSchema,
}).superRefine((row, ctx) => requireValidVllmProvenance(row, ctx));

export const IndexDataSchema = z.object({
  generated_note: z.string(),
  suite_version: z.string().nullable(),
  index_version: z.string(),
  models: z.array(IndexModelSchema),
});

// Supplementary "Agentic" column data from web/public/data/agentic.json. Ranked Index math still
// comes from the board axis registry; this join only displays historical AppWorld-C funnel ASR.
export const AgenticModelSchema = z.object({
  asr: z.number(),
  asr_pct: z.number(),
  n_tasks: z.number(),
  n_runs: z.number(),
  asr_series: z.array(z.number()),
  label: z.string(),
});

export const AgenticDataSchema = z.object({
  schema: z.string(),
  generated_note: z.string(),
  as_of: z.string().nullable(),
  models: z.record(z.string(), AgenticModelSchema),
});

export const ModelRunSchema = z.object({
  run_id: RunIdSchema.nullable(),
  quant_label: z.string().nullable(),
  vram_footprint_gb: z.number().nullable(),
  vram_required_gb_8k: z.number().nullable().optional(),
  file_gb: z.number().nullable().optional(),
  bpw: z.number().nullable().optional(),
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  composite_full: ScoreSchema.nullable().optional(),
  composite_static: ScoreSchema.nullable().optional(),
  axes: AxesSchema,
  axis_status: AxisStatusSchema.optional(),
  tier: z.string().nullable(),
  lane: z.string().nullable(),
  tokens_to_answer_median: z.number().nullable(),
  tokens_to_answer_p95: z.number().nullable().optional(),
  tok_s: z.number().nullable(),
  latency_s_median: z.number().nullable().optional(),
  est_cost_usd: z.number().nullable(),
  hardware: HardwareSchema,
  runtime: RuntimeSchema,
  serving_provenance: ServingProvenanceSchema.optional(),
  n_items: z.number(),
  n_errors: z.number(),
  perf: PerfSchema.optional(),
  ranked: z.boolean().optional().default(false),
  wall_time_seconds: z.number().nullable().optional(),
  score_status: ScoreStatusSchema.optional().default("measured"),
  has_code_artifacts: z.boolean().optional(),
  verdict_source: z.string().nullable().optional(),
  conformance_gates: ConformanceGatesSchema.optional(),
  submitter_display_name: z.string().nullable().optional(),
  origin: BoardOriginSchema.optional(),
  trust_label: z.string().optional(),
  agentic_provenance: AgenticProvenanceSchema.optional(),
  provenance_notes: z.array(z.string()).optional(),
  static_index_version: z.string().optional(),
  demo: DemoFlagSchema,
}).superRefine((row, ctx) => requireValidVllmProvenance(row, ctx));

export const ModelDataSchema = z.object({
  slug: ModelSlugSchema,
  catalog_id: z.string().nullable().optional(),
  model_label: z.string(),
  family: z.string(),
  kind: KindSchema,
  gguf_repo: z.string().nullable().optional(),
  license: z.string().nullable().optional(),
  org: z.string().nullable().optional(),
  model_kind: ModelKindSchema.optional().default("base"),
  demo: DemoFlagSchema,
  runs: z.array(ModelRunSchema),
});

export const ManifestSummarySchema = z.object({
  model: z
    .object({
      family: z.string().nullable(),
      file_name: z.string().nullable(),
      file_sha256: z.string().nullable(),
      file_size_bytes: z.number().nullable(),
      format: z.string().nullable(),
      runtime_reported_model: z.string().nullable(),
    })
    .passthrough(),
  quant: z.string().nullable(),
  runtime: RuntimeSchema,
  hardware: HardwareSchema,
  lane: z.string().nullable(),
  thinking_mode: z.string().nullable(),
  caps: PrimitiveRecordSchema,
  sampling: SamplingSchema,
});

export const RunDetailSchema = z.object({
  run_id: RunIdSchema,
  model_label: z.string(),
  kind: KindSchema,
  tier: z.string(),
  composite: ScoreSchema.nullable(),
  diagnostic_composite: ScoreSchema.nullable().optional(),
  composite_full: ScoreSchema.nullable().optional(),
  composite_static: ScoreSchema.nullable().optional(),
  axes: AxesSchema,
  axis_status: AxisStatusSchema.optional(),
  worst_axis: z.object({
    bench: z.string(),
    point: z.number(),
    point_raw: z.number(),
  }),
  manifest_summary: ManifestSummarySchema,
  ranked: z.boolean().optional().default(false),
  scorecard: ScorecardSummarySchema.optional(),
  serving_provenance: ServingProvenanceSchema.optional(),
  has_code_artifacts: z.boolean().optional(),
  verdict_source: z.string().nullable().optional(),
  totals: TotalsSchema,
  perf: PerfSchema.optional(),
  est_cost_usd: z.number().nullable(),
  tokens_to_answer_median: z.number().nullable(),
  tokens_to_answer_p95: z.number().nullable(),
  item_set_hashes: z.record(z.string(), z.string()),
  suite_version: z.string(),
  index_version: z.string(),
  data_warnings: z.array(z.string()).optional(),
  submitter_display_name: z.string().nullable().optional(),
  origin: BoardOriginSchema.optional(),
  trust_label: z.string().optional(),
  agentic_provenance: AgenticProvenanceSchema.optional(),
  provenance_notes: z.array(z.string()).optional(),
  static_index_version: z.string().optional(),
  lane: z.string().nullable().optional(),
  score_status: ScoreStatusSchema.optional().default("measured"),
  demo: DemoFlagSchema,
}).superRefine((row, ctx) => requireValidVllmProvenance({ runtime: row.manifest_summary.runtime, serving_provenance: row.serving_provenance }, ctx));

export type Axis = string;
export type Score = z.infer<typeof ScoreSchema>;
export type AxisScore = z.infer<typeof AxisScoreSchema>;
export type ScorecardSummary = z.infer<typeof ScorecardSummarySchema>;
export type ConformanceGate = z.infer<typeof ConformanceGateSchema>;
export type ConformanceGates = z.infer<typeof ConformanceGatesSchema>;
export type Kind = z.infer<typeof KindSchema>;
export type ScoreStatus = z.infer<typeof ScoreStatusSchema>;
export type BoardOrigin = z.infer<typeof BoardOriginSchema>;
export type AgenticProvenance = z.infer<typeof AgenticProvenanceSchema>;
export type ModelKind = z.infer<typeof ModelKindSchema>;
export type IndexData = z.infer<typeof IndexDataSchema>;
export type IndexModel = z.infer<typeof IndexModelSchema>;
export type AgenticModel = z.infer<typeof AgenticModelSchema>;
export type AgenticData = z.infer<typeof AgenticDataSchema>;
export type ModelData = z.infer<typeof ModelDataSchema>;
export type ModelRun = z.infer<typeof ModelRunSchema>;
export type RunDetail = z.infer<typeof RunDetailSchema>;
export type RuntimeSummary = z.infer<typeof RuntimeSchema>;
export type HardwareSummary = z.infer<typeof HardwareSchema>;
export type PrimitiveRecord = z.infer<typeof PrimitiveRecordSchema>;
export type Perf = z.infer<typeof PerfSchema>;
export type ServingProvenance = z.infer<typeof ServingProvenanceSchema>;

// Raw shape of model_catalog.json (the on-ramp picker source). Tolerant by design — the catalog is
// large and varied, so unknown keys pass through and most fields are optional/nullable.
const CatalogArtifactFileSchema = z
  .object({
    filename: z.string(),
    file_size_bytes: z.number().int().nonnegative(),
    file_sha256: FullSha256Schema,
  })
  .passthrough();

const CatalogQuantSchema = z
  .object({
    label: z.string(),
    bpw: z.number().nullable().optional(),
    file_gb: z.number().nullable().optional(),
    vram_gb_8k: z.number().nullable().optional(),
    gguf_repo: z.string().nullable().optional(),
    filename: z.string().nullable().optional(),
    revision: FullShaSchema.nullable().optional(),
    file_size_bytes: z.number().int().nonnegative().nullable().optional(),
    file_sha256: FullSha256Schema.nullable().optional(),
    artifact_files: z.array(CatalogArtifactFileSchema).optional(),
  })
  .passthrough();

const CatalogModelSchema = z
  .object({
    id: z.string(),
    slug: z.string(),
    display_name: z.string(),
    family: z.string().nullable().optional(),
    org: z.string().nullable().optional(),
    params_b: z
      .union([
        z.number(),
        z.object({ total_b: z.number().nullable().optional(), active_b: z.number().nullable().optional() }).passthrough(),
      ])
      .nullable()
      .optional(),
    reasoning_capable: z.boolean().nullable().optional(),
    license: z.string().nullable().optional(),
    base_model: z.union([z.string(), z.array(z.string())]).nullable().optional(),
    model_kind: ModelKindSchema.optional().default("base"),
    popularity: z
      .object({
        downloads: z.number().nullable().optional(),
        likes: z.number().nullable().optional(),
        trending: z.number().nullable().optional(),
      })
      .passthrough()
      .nullable()
      .optional(),
    gguf_repo: z.string().nullable().optional(),
    quants: z.array(CatalogQuantSchema),
  })
  .passthrough();

export const CatalogSchema = z.union([
  z.array(CatalogModelSchema),
  z
    .object({
      popularity_as_of: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
      models: z.array(CatalogModelSchema),
    })
    .passthrough(),
]);
export type CatalogModel = z.infer<typeof CatalogModelSchema>;
export type Catalog = z.infer<typeof CatalogSchema>;

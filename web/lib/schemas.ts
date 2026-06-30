import { z } from "zod";

export const ModelSlugSchema = z.string().min(1).brand<"ModelSlug">();
export const RunIdSchema = z.string().min(1).brand<"RunId">();

const JsonPrimitiveSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const PrimitiveRecordSchema = z.record(z.string(), JsonPrimitiveSchema);

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
  // IFBench strict decomposition (present once strict-scored run JSONs are wired; flat per the
  // producer's shape — see docs/SITE-DATA-CONTRACT.md). raw_accuracy above IS the strict accuracy.
  termination_rate: z.number().optional(),
  conditional_accuracy: z.number().optional(),
});

export const AxesSchema = z.record(z.string(), AxisScoreSchema);
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
  id: z.string().nullable(),
  registry_digest: z.string().nullable().optional(),
  registry_drift: z.boolean().optional(),
  version: z.string().nullable(),
});

export const KindSchema = z.enum(["anchor", "community"]);
export const ScoreStatusSchema = z.enum(["measured", "missing"]);
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
  name: z.string().nullable(),
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

export const IndexModelSchema = z.object({
  slug: ModelSlugSchema,
  catalog_id: z.string().nullable().optional(),
  model_label: z.string(),
  family: z.string(),
  kind: KindSchema,
  best_run_id: RunIdSchema.nullable(),
  composite: ScoreSchema.nullable(),
  axes: AxesSchema,
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
  // V2 stub: who submitted the top run (community submissions). Absent in v1 (maintainer-only,
  // anonymous), so the User column renders a neutral placeholder.
  submitted_by: z.string().nullable().optional(),
  replicated: z.boolean(),
  score_status: ScoreStatusSchema.optional().default("measured"),
  conformance_gates: ConformanceGatesSchema.optional(),
  demo: DemoFlagSchema,
});

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
  axes: AxesSchema,
  tier: z.string().nullable(),
  lane: z.string().nullable(),
  tokens_to_answer_median: z.number().nullable(),
  tokens_to_answer_p95: z.number().nullable().optional(),
  tok_s: z.number().nullable(),
  latency_s_median: z.number().nullable().optional(),
  est_cost_usd: z.number().nullable(),
  hardware: HardwareSchema,
  runtime: RuntimeSchema,
  n_items: z.number(),
  n_errors: z.number(),
  ranked: z.boolean().optional().default(false),
  wall_time_seconds: z.number().nullable().optional(),
  score_status: ScoreStatusSchema.optional().default("measured"),
  conformance_gates: ConformanceGatesSchema.optional(),
  demo: DemoFlagSchema,
});

export const ModelDataSchema = z.object({
  slug: ModelSlugSchema,
  catalog_id: z.string().nullable().optional(),
  model_label: z.string(),
  family: z.string(),
  kind: KindSchema,
  gguf_repo: z.string().nullable().optional(),
  license: z.string().nullable().optional(),
  org: z.string().nullable().optional(),
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
  composite: ScoreSchema,
  axes: AxesSchema,
  worst_axis: z.object({
    bench: z.string(),
    point: z.number(),
    point_raw: z.number(),
  }),
  manifest_summary: ManifestSummarySchema,
  ranked: z.boolean().optional().default(false),
  scorecard: ScorecardSummarySchema.optional(),
  totals: TotalsSchema,
  est_cost_usd: z.number().nullable(),
  tokens_to_answer_median: z.number().nullable(),
  tokens_to_answer_p95: z.number().nullable(),
  item_set_hashes: z.record(z.string(), z.string()),
  suite_version: z.string(),
  index_version: z.string(),
  data_warnings: z.array(z.string()).optional(),
  demo: DemoFlagSchema,
});

export type Axis = string;
export type Score = z.infer<typeof ScoreSchema>;
export type AxisScore = z.infer<typeof AxisScoreSchema>;
export type ScorecardSummary = z.infer<typeof ScorecardSummarySchema>;
export type ConformanceGate = z.infer<typeof ConformanceGateSchema>;
export type ConformanceGates = z.infer<typeof ConformanceGatesSchema>;
export type Kind = z.infer<typeof KindSchema>;
export type ScoreStatus = z.infer<typeof ScoreStatusSchema>;
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

// Raw shape of model_catalog.json (the on-ramp picker source). Tolerant by design — the catalog is
// large and varied, so unknown keys pass through and most fields are optional/nullable.
const CatalogQuantSchema = z
  .object({
    label: z.string(),
    bpw: z.number().nullable().optional(),
    file_gb: z.number().nullable().optional(),
    vram_gb_8k: z.number().nullable().optional(),
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
    popularity: z.object({ downloads: z.number().nullable().optional() }).passthrough().nullable().optional(),
    gguf_repo: z.string().nullable().optional(),
    quants: z.array(CatalogQuantSchema),
  })
  .passthrough();

export const CatalogSchema = z.array(CatalogModelSchema);
export type CatalogModel = z.infer<typeof CatalogModelSchema>;

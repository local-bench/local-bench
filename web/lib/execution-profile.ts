import { z } from "zod";

const SAFE_TEXT_RE = /^[^\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+$/u;
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/u);
const ProfileTextSchema = z.string().min(1).max(160).regex(SAFE_TEXT_RE);

export const CURRENT_EXECUTION_PROFILE_ID = "generic_think_tags_32768_v1" as const;

const ExecutionProfileBaseShape = {
  answer_stops: z.array(ProfileTextSchema).max(16).readonly(),
  chat_template_kwargs: z.record(ProfileTextSchema, z.boolean())
    .refine((value) => Object.keys(value).length <= 16)
    .readonly(),
  id: ProfileTextSchema,
  prompt_renderer_engine: ProfileTextSchema,
  runtime_probe_passed: z.boolean(),
  selection_policy_id: ProfileTextSchema,
  selection_reason: ProfileTextSchema,
  template_sha256: Sha256Schema.nullable(),
  template_source: ProfileTextSchema,
} as const;

const LegacySemanticShape = {
  agentic_context_tokens: z.number().int().positive().optional(),
  agentic_max_generated_tokens_per_task: z.number().int().positive().optional(),
  agentic_max_output_tokens_per_turn: z.number().int().positive().optional(),
  agentic_max_turns: z.number().int().positive().optional(),
  context_extension_policy: z.literal("none").optional(),
  context_fit_policy: z.literal("exact-or-fail").optional(),
  kv_cache_k_dtype: z.literal("f16").optional(),
  kv_cache_v_dtype: z.literal("f16").optional(),
  per_task_timeout_s: z.number().int().positive().optional(),
  semantic_sha256: Sha256Schema.optional(),
  server_context_tokens: z.number().int().positive().optional(),
  static_final_tokens: z.number().int().positive().optional(),
  static_max_generated_tokens: z.number().int().positive().optional(),
  static_think_tokens: z.number().int().positive().optional(),
} as const;

const ExecutionProfileV1Schema = z.object({
  ...ExecutionProfileBaseShape,
  ...LegacySemanticShape,
  id: ProfileTextSchema.refine((value) => value !== CURRENT_EXECUTION_PROFILE_ID),
  schema_version: z.undefined().optional(),
}).strict().readonly();

const ExecutionProfileV2Schema = z.object({
  ...ExecutionProfileBaseShape,
  agentic_context_tokens: z.literal(32768),
  agentic_max_generated_tokens_per_task: z.literal(65536),
  agentic_max_output_tokens_per_turn: z.literal(1024),
  agentic_max_turns: z.literal(40),
  context_extension_policy: z.literal("none"),
  context_fit_policy: z.literal("exact-or-fail"),
  id: z.literal(CURRENT_EXECUTION_PROFILE_ID),
  kv_cache_k_dtype: z.literal("f16"),
  kv_cache_v_dtype: z.literal("f16"),
  per_task_timeout_s: z.literal(3000),
  schema_version: z.literal("localbench.execution_profile.v2"),
  semantic_sha256: z.literal("e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058"),
  server_context_tokens: z.literal(65536),
  static_final_tokens: z.literal(16384),
  static_max_generated_tokens: z.literal(49152),
  static_think_tokens: z.literal(32768),
}).strict().readonly();

export const PublicExecutionProfileSchema = z.discriminatedUnion("schema_version", [
  ExecutionProfileV1Schema,
  ExecutionProfileV2Schema,
]);

export const ExecutionProfileSchema = PublicExecutionProfileSchema;

export const LegacyExecutionProfileReferenceSchema = z.object({
  id: ProfileTextSchema.refine((value) => value !== CURRENT_EXECUTION_PROFILE_ID),
}).strict().readonly();

export const BoardExecutionProfileSchema = z.union([
  PublicExecutionProfileSchema,
  LegacyExecutionProfileReferenceSchema,
]);

export type ExecutionProfile = z.infer<typeof ExecutionProfileSchema>;
export type PublicExecutionProfile = z.infer<typeof PublicExecutionProfileSchema>;
export type LegacyExecutionProfileReference = z.infer<typeof LegacyExecutionProfileReferenceSchema>;
export type BoardExecutionProfile = z.infer<typeof BoardExecutionProfileSchema>;
export type CommunityExecutionProfileFields = {
  readonly executionProfile?: BoardExecutionProfile;
  readonly supersedesSubmissionId?: string;
};

export function isCurrentExecutionProfile(
  profile: BoardExecutionProfile | undefined,
): boolean {
  return profile?.id === CURRENT_EXECUTION_PROFILE_ID;
}

export function executionProfileSemanticSha256(
  profile: BoardExecutionProfile | undefined,
): string | undefined {
  return profile !== undefined && "semantic_sha256" in profile
    ? profile.semantic_sha256
    : undefined;
}

export function matchingCompleteSemanticDigests(
  left: string | undefined,
  right: string | undefined,
): boolean {
  return left !== undefined && Sha256Schema.safeParse(left).success && left === right;
}

export function executionProfileSummary(profile: BoardExecutionProfile): string {
  if ("static_think_tokens" in profile && profile.static_think_tokens !== undefined) {
    const parts = [`${formatBudget(profile.static_think_tokens)} reasoning`];
    if (profile.static_final_tokens !== undefined) {
      parts.push(`${formatBudget(profile.static_final_tokens)} final`);
    }
    if (profile.server_context_tokens !== undefined) {
      parts.push(`${formatBudget(profile.server_context_tokens)} context`);
    }
    return parts.join(" · ");
  }
  if (profile.id === "answer_only_8192_v1") return "8k answer-only";
  if (profile.id.includes("8192")) return "8k static reasoning";
  return "historical execution profile";
}

function formatBudget(tokens: number): string {
  return tokens % 1024 === 0 ? `${tokens / 1024}k` : tokens.toLocaleString("en-US");
}

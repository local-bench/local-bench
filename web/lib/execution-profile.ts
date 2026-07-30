import { z } from "zod";

const SAFE_TEXT_RE = /^[^\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+$/u;
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/u);
const ProfileTextSchema = z.string().min(1).max(160).regex(SAFE_TEXT_RE);

export const ExecutionProfileSchema = z.object({
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
}).strict().readonly();

export const PublicExecutionProfileSchema = z.union([
  ExecutionProfileSchema,
  z.object({ id: ProfileTextSchema }).strict().readonly(),
]);

export type ExecutionProfile = z.infer<typeof ExecutionProfileSchema>;
export type PublicExecutionProfile = z.infer<typeof PublicExecutionProfileSchema>;
export type CommunityExecutionProfileFields = {
  readonly executionProfile?: PublicExecutionProfile;
  readonly supersedesSubmissionId?: string;
};

import { describe, expect, it } from "vitest";
import {
  PublicExecutionProfileSchema,
  type PublicExecutionProfile,
} from "../lib/execution-profile";

const LEGACY_V1 = {
  answer_stops: ["<|im_end|>"],
  chat_template_kwargs: { enable_thinking: true },
  id: "generic_think_tags_8192_v1",
  prompt_renderer_engine: "llama.cpp.apply-template",
  runtime_probe_passed: true,
  selection_policy_id: "gguf-effective-template-v1",
  selection_reason: "gguf_generic_think_confirmed",
  template_sha256: "a".repeat(64),
  template_source: "gguf-default",
} as const;

const PROFILE_V2 = {
  ...LEGACY_V1,
  agentic_context_tokens: 32768,
  agentic_max_generated_tokens_per_task: 65536,
  agentic_max_output_tokens_per_turn: 1024,
  agentic_max_turns: 40,
  context_extension_policy: "none",
  context_fit_policy: "exact-or-fail",
  id: "generic_think_tags_32768_v1",
  kv_cache_k_dtype: "f16",
  kv_cache_v_dtype: "f16",
  per_task_timeout_s: 3000,
  schema_version: "localbench.execution_profile.v2",
  semantic_sha256: "e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058",
  server_context_tokens: 65536,
  static_final_tokens: 16384,
  static_max_generated_tokens: 49152,
  static_think_tokens: 32768,
} as const;

const BASE_T2_V1 = {
  ...LEGACY_V1,
  agentic_context_tokens: 32768,
  agentic_max_generated_tokens_per_task: 32768,
  agentic_max_output_tokens_per_turn: 1024,
  agentic_max_turns: 24,
  context_extension_policy: "none",
  context_fit_policy: "exact-or-fail",
  kv_cache_k_dtype: "f16",
  kv_cache_v_dtype: "f16",
  per_task_timeout_s: 1800,
  semantic_sha256: "a6bf105b73ad3f8120751151707ce2d15f4b20617a64250679a0dce8977d9bb3",
  server_context_tokens: 32768,
  static_final_tokens: 8192,
  static_max_generated_tokens: 16384,
  static_think_tokens: 8192,
} as const;

function staticThinkTokens(profile: PublicExecutionProfile): number | undefined {
  switch (profile.schema_version) {
    case undefined:
      return profile.static_think_tokens;
    case "localbench.execution_profile.v2":
      return profile.static_think_tokens;
    default:
      return assertNever(profile);
  }
}

function assertNever(value: never): never {
  throw new Error(`unexpected execution profile: ${JSON.stringify(value)}`);
}

describe("public execution-profile contract", () => {
  it("parses an unchanged legacy v1 structured row", () => {
    // Given / When: a 0.4.12/0.4.13 row crosses the site boundary.
    const parsed = PublicExecutionProfileSchema.parse(LEGACY_V1);

    // Then: it remains byte-shape compatible.
    expect(parsed).toEqual(LEGACY_V1);
  });

  it("preserves the exact enriched 8192 record emitted at BASE", () => {
    // Given / When: the 23-field T2-era record crosses the site boundary.
    const parsed = PublicExecutionProfileSchema.parse(BASE_T2_V1);

    // Then: v1 optional semantic identity remains intact and narrows exhaustively.
    expect(parsed).toEqual(BASE_T2_V1);
    expect(staticThinkTokens(parsed)).toBe(8192);
  });

  it("parses a complete 32768-v2 row", () => {
    // Given / When: the complete minted tuple crosses the site boundary.
    const parsed = PublicExecutionProfileSchema.parse(PROFILE_V2);

    // Then: its discriminator and semantic identity survive parsing.
    expect(parsed).toEqual(PROFILE_V2);
  });

  it("rejects incomplete and inconsistent 32768-v2 rows", () => {
    // Given: one incomplete record and one tuple/digest mismatch.
    const { agentic_max_turns: _missing, ...incomplete } = PROFILE_V2;
    const inconsistent = { ...PROFILE_V2, agentic_max_turns: 39 };
    const idOnly = { id: "generic_think_tags_32768_v1" };

    // When / Then: neither record can cross the public contract boundary.
    expect(PublicExecutionProfileSchema.safeParse(incomplete).success).toBe(false);
    expect(PublicExecutionProfileSchema.safeParse(inconsistent).success).toBe(false);
    expect(PublicExecutionProfileSchema.safeParse(idOnly).success).toBe(false);
  });
});

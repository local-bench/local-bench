import type { PublicExecutionProfile } from "../../lib/execution-profile";

const GENERIC_THINK_PROFILE_ID = "generic_think_tags_8192_v1";

export const KNOWN_EXECUTION_PROFILES: Readonly<Record<string, string>> = Object.freeze({
  ticket_02949bd2dddd41908b65d76a97b3c648: GENERIC_THINK_PROFILE_ID,
  ticket_75e2314e2a81417fb11b6396d3ebea35: GENERIC_THINK_PROFILE_ID,
  ticket_783cba6e5d2e42a786823884da1fcd15: GENERIC_THINK_PROFILE_ID,
  ticket_cc352811a58d4022b3044eb28abce178: GENERIC_THINK_PROFILE_ID,
  ticket_d65715b80b6f4e2fa54d63ca7ce5273b: GENERIC_THINK_PROFILE_ID,
});

export const SUPERSEDES: Readonly<Record<string, string>> = Object.freeze({});

type ExecutionProfilePolicyInput = {
  readonly complete: boolean;
  readonly runtimeName: string | null;
  readonly structuredProfile: PublicExecutionProfile | undefined;
  readonly submissionId: string;
};

type ExecutionProfilePolicy = {
  readonly executionProfile: PublicExecutionProfile | undefined;
  readonly moderationQueueMarker: "legacy_execution_profile_review" | undefined;
  readonly supersedesSubmissionId: string | undefined;
};

export function executionProfilePolicy(input: ExecutionProfilePolicyInput): ExecutionProfilePolicy {
  const knownId = KNOWN_EXECUTION_PROFILES[input.submissionId];
  const executionProfile = input.structuredProfile
    ?? (knownId === undefined ? undefined : { id: knownId });
  // B6 admission gate: every COMPLETE llama.cpp row must carry a verified execution
  // profile (structured field from a 0.4.12+ client, or a maintainer mapping for the
  // archived rows). HF identity is deliberately NOT part of this predicate — the row
  // class the gate exists for (pre-0.4.12 --gguf-repo-only submissions, which ran an
  // unexamined profile) has NO hf identity, so conditioning on hf would exempt exactly
  // the rows that are not provably ranked-safe.
  const requiresExecutionProfile = input.complete
    && input.runtimeName === "llama.cpp";
  return {
    executionProfile,
    moderationQueueMarker: requiresExecutionProfile && executionProfile === undefined
      ? "legacy_execution_profile_review"
      : undefined,
    supersedesSubmissionId: SUPERSEDES[input.submissionId],
  };
}

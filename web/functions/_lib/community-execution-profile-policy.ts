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
  readonly hasHfIdentity: boolean;
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
  const requiresExecutionProfile = input.complete
    && input.hasHfIdentity
    && input.runtimeName === "llama.cpp";
  return {
    executionProfile,
    moderationQueueMarker: requiresExecutionProfile && executionProfile === undefined
      ? "legacy_execution_profile_review"
      : undefined,
    supersedesSubmissionId: SUPERSEDES[input.submissionId],
  };
}

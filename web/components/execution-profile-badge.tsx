import {
  executionProfileCohort,
  executionProfileSummary,
  type BoardExecutionProfile,
} from "@/lib/execution-profile";

export function ExecutionProfileBadge({
  profile,
}: {
  readonly profile: BoardExecutionProfile;
}) {
  const state = executionProfileCohort(profile) === "32k" ? "32k" : "8k";
  const deeper = state === "32k";
  const summary = executionProfileSummary(profile);
  return (
    <span
      aria-label={`${state} operating point: ${summary}. Execution profile ${profile.id}`}
      className="inline-flex max-w-full flex-wrap items-center gap-1.5"
      title={`execution profile: ${profile.id}`}
    >
      <span className={deeper
        ? "rounded border border-bench-accent/45 bg-bench-accent/[0.10] px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-accent"
        : "rounded border border-bench-mixed/45 bg-bench-mixed/[0.10] px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-mixed"}
      >
        {state}
      </span>
      <span className="text-xs leading-5 text-bench-muted">{summary}</span>
    </span>
  );
}

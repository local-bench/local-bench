import type { PublicExecutionProfile } from "@/lib/execution-profile";

export function ExecutionProfileBadge({
  profile,
}: {
  readonly profile: PublicExecutionProfile;
}) {
  const label = profile.id === "generic_think_tags_8192_v1"
    ? "generic think"
    : profile.id === "answer_only_8192_v1"
      ? "answer only"
      : "execution profile";
  return (
    <span
      className="inline-flex rounded border border-bench-accent/35 bg-bench-accent/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-bench-accent"
      title={`execution profile: ${profile.id}`}
    >
      {label}
    </span>
  );
}

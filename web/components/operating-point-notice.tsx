import { isCurrentExecutionProfile, type BoardExecutionProfile } from "@/lib/execution-profile";

export const OPERATING_POINT_NOTICE = "Operating point changed from 8k static reasoning to 32k. Cross-profile scores are not compute-matched." as const;

export function OperatingPointNotice({
  profiles,
}: {
  readonly profiles: readonly (BoardExecutionProfile | undefined)[];
}) {
  if (!profiles.some(isCurrentExecutionProfile)) return null;
  return (
    <p
      role="status"
      className="border-b border-bench-warn/40 bg-bench-warn/[0.08] px-4 py-3 text-sm leading-6 text-bench-text"
    >
      {OPERATING_POINT_NOTICE}
    </p>
  );
}

import { isCurrentExecutionProfile, type BoardExecutionProfile } from "@/lib/execution-profile";
import type {
  BoardDefaultOperatingPointView,
  OperatingPointView,
} from "@/lib/operating-point-view";

export const OPERATING_POINT_NOTICE = "Operating point changed from 8k static reasoning to 32k. Cross-profile scores are not compute-matched." as const;

export function OperatingPointNotice({
  defaultView,
  profiles,
  view,
}: {
  readonly defaultView: BoardDefaultOperatingPointView;
  readonly profiles: readonly (BoardExecutionProfile | undefined)[];
  readonly view: OperatingPointView;
}) {
  const visible = defaultView === "mixed"
    ? view === "mixed" && profiles.some(isCurrentExecutionProfile)
    : view === "archived-8k";
  if (!visible) return null;
  return (
    <p
      role="status"
      className="border-b border-bench-warn/40 bg-bench-warn/[0.08] px-4 py-3 text-sm leading-6 text-bench-text"
    >
      {OPERATING_POINT_NOTICE}
    </p>
  );
}

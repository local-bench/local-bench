import type { ExecutionProfileCohort } from "./execution-profile";

export type BoardDefaultOperatingPointView = "mixed" | "32k-default";
export type OperatingPointView = "mixed" | "32k" | "archived-8k";

export const BOARD_DEFAULT_OPERATING_POINT_VIEW: BoardDefaultOperatingPointView = "mixed";
export const OPERATING_POINT_QUERY_PARAM = "operating-point" as const;
export const ARCHIVED_OPERATING_POINT_LABEL = "archived operating point (2026-07, 8k)" as const;

export function resolveOperatingPointView(
  defaultView: BoardDefaultOperatingPointView,
  queryValue: string | null,
): OperatingPointView {
  if (queryValue === "mixed" || queryValue === "32k" || queryValue === "archived-8k") {
    return queryValue;
  }
  return defaultView === "mixed" ? "mixed" : "32k";
}

export function operatingPointViewHref(view: OperatingPointView): string {
  return `?${OPERATING_POINT_QUERY_PARAM}=${view}`;
}

export function operatingPointViewIncludesCohort(
  view: OperatingPointView,
  cohort: ExecutionProfileCohort,
): boolean {
  if (view === "mixed") return true;
  if (view === "32k") return cohort === "32k";
  return cohort !== "32k";
}

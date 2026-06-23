import { formatScore } from "@/lib/format";
import type { AxisScore } from "@/lib/schemas";

export const LOCAL_INTELLIGENCE_INDEX_NAME = "Local Intelligence Index";
export const LOCAL_INTELLIGENCE_INDEX_QUALIFIER = "v1 · Knowledge + Instruction";
export const LOCAL_INTELLIGENCE_INDEX_PROFILE = "Profile: Knowledge / Instruction";

const CORE_TEXT_AXES = [
  { key: "knowledge", label: "Knowledge" },
  { key: "instruction", label: "Instruction" },
] as const;

export function CoreTextAxisProfile({
  axes,
  className = "",
}: {
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly className?: string;
}) {
  return <span className={className}>{formatCoreTextAxisProfile(axes)}</span>;
}

export function LocalIntelligenceIndexScope({ className = "" }: { readonly className?: string }) {
  return <span className={className}>{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>;
}

export function formatCoreTextAxisProfile(axes: Readonly<Record<string, AxisScore>>): string {
  return CORE_TEXT_AXES.map(({ key, label }) => {
    const score = axes[key];
    return `${label} ${score === undefined ? "n/a" : formatScore(score.point)}`;
  }).join(" / ");
}

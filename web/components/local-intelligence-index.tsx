import { formatScore } from "@/lib/format";
import type { AxisScore } from "@/lib/schemas";

export const LOCAL_INTELLIGENCE_INDEX_NAME = "Local Intelligence Index";
export const LOCAL_INTELLIGENCE_INDEX_QUALIFIER = "index-v3.0 | 40/15/15/10/15/5";
export const LOCAL_INTELLIGENCE_INDEX_PROFILE = "Profile: Agentic / Knowledge / Instruction / Tool calling / Coding / Math";

const HEADLINE_AXES = [
  { key: "agentic", label: "Agentic" },
  { key: "knowledge", label: "Knowledge" },
  { key: "instruction", label: "Instruction" },
  { key: "tool_calling", label: "Tool" },
  { key: "coding", label: "Coding" },
  { key: "math", label: "Math" },
] as const;

export function ModularAxisProfile({
  axes,
  className = "",
}: {
  readonly axes: Readonly<Record<string, AxisScore>>;
  readonly className?: string;
}) {
  return <span className={className}>{formatModularAxisProfile(axes)}</span>;
}

export function LocalIntelligenceIndexScope({ className = "" }: { readonly className?: string }) {
  return <span className={className}>{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>;
}

export function formatModularAxisProfile(axes: Readonly<Record<string, AxisScore>>): string {
  return HEADLINE_AXES.map(({ key, label }) => {
    const score = axes[key];
    return `${label} ${score === undefined ? "n/a" : formatScore(score.point)}`;
  }).join(" / ");
}

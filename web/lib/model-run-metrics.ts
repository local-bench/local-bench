import {
  DEFAULT_CONTEXT_TOKENS,
  estimateVramRequirement,
  type ContextLengthOption,
  type VramEstimate,
} from "./rig-match";
import type { ModelRun } from "./schemas";

type ArtifactMetricRun = Pick<
  ModelRun,
  "file_gb" | "quant_label" | "score_status" | "vram_footprint_gb" | "vram_required_gb_8k"
>;

export type ResolvedRunArtifactMetrics = {
  readonly fileGb: number | null;
  readonly vramRequiredGb8k: number | null;
};

export function resolveRunArtifactMetrics(
  run: ArtifactMetricRun,
  siblingRuns: readonly ArtifactMetricRun[],
): ResolvedRunArtifactMetrics {
  const candidates = siblingRuns.filter((candidate) =>
    candidate !== run &&
    candidate.quant_label === run.quant_label &&
    (candidate.file_gb != null || candidate.vram_required_gb_8k != null));
  const sibling = candidates.find((candidate) => candidate.score_status !== "measured") ?? candidates[0];

  return {
    fileGb: run.file_gb ?? sibling?.file_gb ?? null,
    vramRequiredGb8k: run.vram_required_gb_8k ?? sibling?.vram_required_gb_8k ?? null,
  };
}

export function estimateRunVram(
  run: ArtifactMetricRun,
  siblingRuns: readonly ArtifactMetricRun[],
  contextTokens: ContextLengthOption = DEFAULT_CONTEXT_TOKENS,
): VramEstimate | null {
  const resolved = resolveRunArtifactMetrics(run, siblingRuns);
  return estimateVramRequirement({
    quantLabel: run.quant_label,
    vramFootprintGb: run.vram_footprint_gb,
    vramRequiredGb8k: resolved.vramRequiredGb8k,
  }, contextTokens);
}

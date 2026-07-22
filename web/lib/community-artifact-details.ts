import type { ModelData } from "./schemas";

export type CommunityArtifactDetail = {
  readonly artifactSha256: string;
  readonly fileGb: number | null;
  readonly modelLabel: string;
  readonly quantLabel: string | null;
  readonly slug: string;
  readonly vramGb8k: number | null;
};

export function communityArtifactDetails(
  models: readonly Pick<ModelData, "artifacts" | "model_label" | "slug">[],
): readonly CommunityArtifactDetail[] {
  return models.flatMap((model) => (model.artifacts ?? []).map((artifact) => ({
    artifactSha256: artifact.file_sha256,
    fileGb: artifact.file_gb ?? null,
    modelLabel: model.model_label,
    quantLabel: typeof artifact["quant_label"] === "string" ? artifact["quant_label"] : null,
    slug: model.slug,
    vramGb8k: artifact.vram_gb_8k ?? null,
  })));
}

export function communityArtifactDetailForSha(
  details: readonly CommunityArtifactDetail[],
  artifactSha256: string,
): CommunityArtifactDetail | undefined {
  return details.find((detail) => detail.artifactSha256 === artifactSha256);
}

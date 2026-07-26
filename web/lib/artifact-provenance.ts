import { z } from "zod";
import type { ModelData } from "./schemas";

const SHA256_RE = /^[0-9a-f]{64}$/u;
const REPO_ID_RE = /^[^/\s]+\/[^/\s]+$/u;
const VERIFIED_AT_RE = /^\d{4}-\d{2}-\d{2}$/u;

const ArtifactProvenanceRegistryEntrySchema = z.object({
  filename: z.string().min(1),
  repo_id: z.string().regex(REPO_ID_RE),
  revision: z.string().min(1),
  verified: z.literal("hf-lfs-oid"),
  verified_at: z.string().regex(VERIFIED_AT_RE),
}).strict().readonly();

export const ArtifactProvenanceRegistrySchema = z.record(
  z.string().regex(SHA256_RE),
  ArtifactProvenanceRegistryEntrySchema,
).readonly();

export type ArtifactProvenance = {
  readonly filename: string;
  readonly repo_id: string;
  readonly revision: string;
};

export type ArtifactProvenanceRegistry = z.infer<typeof ArtifactProvenanceRegistrySchema>;

type CatalogArtifact = NonNullable<ModelData["artifacts"]>[number];

export function resolveArtifactProvenance(
  artifactSha256: string,
  catalogArtifacts: readonly CatalogArtifact[],
  registry: Readonly<Record<string, ArtifactProvenance>>,
): ArtifactProvenance | null {
  const catalogArtifact = catalogArtifacts.find((artifact) => artifact.file_sha256 === artifactSha256);
  if (
    catalogArtifact !== undefined
    && catalogArtifact.filename !== undefined
    && catalogArtifact.repo_id !== undefined
    && catalogArtifact.revision !== undefined
  ) {
    return {
      filename: catalogArtifact.filename,
      repo_id: catalogArtifact.repo_id,
      revision: catalogArtifact.revision,
    };
  }
  return registry[artifactSha256] ?? null;
}

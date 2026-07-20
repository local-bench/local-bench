import { z } from "zod";
import overlayJson from "../community_lineage_overlay.json";
import type { CommunityLineage } from "./community-data";

const SHA256_RE = /^[0-9a-f]{64}$/u;
const REVISION_RE = /^[0-9a-f]{40}$/u;

const OverlayLineageSchema = z.object({
  artifact_sha256: z.string().regex(SHA256_RE),
  association: z.object({
    artifact_to_repo: z.literal("unverified"),
    basis: z.literal("maintainer-associated"),
    note: z.string(),
  }).strict().readonly(),
  card_declared_edges: z.array(z.object({
    base: z.string(),
    base_revision: z.string().regex(REVISION_RE).nullable(),
    child: z.string(),
    child_revision: z.string().regex(REVISION_RE),
    source: z.enum(["hf-model-card", "maintainer-asserted"]),
  }).strict().readonly()).readonly(),
  repo: z.object({
    id: z.string(),
    revision: z.string().regex(REVISION_RE),
  }).strict().readonly(),
  resolution: z.object({
    resolved_at: z.string().datetime(),
    status: z.enum(["complete", "truncated", "partial"]),
  }).strict().readonly(),
}).strict().readonly();

const OverlaySchema = z.object({
  entries: z.record(z.string().regex(SHA256_RE), OverlayLineageSchema),
  schema_version: z.literal("localbench.community_lineage_overlay.v1"),
}).strict().readonly();

let cachedOverlay: ReadonlyMap<string, CommunityLineage> | undefined;

export function overlayLineageByArtifactSha(): ReadonlyMap<string, CommunityLineage> {
  if (cachedOverlay !== undefined) return cachedOverlay;
  const parsed = OverlaySchema.safeParse(overlayJson);
  cachedOverlay = parsed.success
    ? new Map(Object.entries(parsed.data.entries).filter(([sha, lineage]) => sha === lineage.artifact_sha256))
    : new Map();
  return cachedOverlay;
}

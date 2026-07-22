import { z } from "zod";
import overlayJson from "../community_origin_overlay.json";

const SHA256_RE = /^[0-9a-f]{64}$/u;
const SUBMISSION_ID_RE = /^ticket_[0-9a-f]{32}$/u;

const OriginOverlayEntrySchema = z.object({
  origin: z.literal("project_anchor"),
  submission_id: z.string().regex(SUBMISSION_ID_RE),
}).strict().readonly();

const OriginOverlaySchema = z.record(z.string().regex(SHA256_RE), OriginOverlayEntrySchema).readonly();

export type CommunityOriginOverlayEntry = z.infer<typeof OriginOverlayEntrySchema>;

let cachedOverlay: ReadonlyMap<string, CommunityOriginOverlayEntry> | undefined;

function originOverlayByArtifactSha(): ReadonlyMap<string, CommunityOriginOverlayEntry> {
  if (cachedOverlay !== undefined) return cachedOverlay;
  const parsed = OriginOverlaySchema.safeParse(overlayJson);
  cachedOverlay = parsed.success ? new Map(Object.entries(parsed.data)) : new Map();
  return cachedOverlay;
}

export function bakedCommunityOrigin(
  artifactSha256: string,
  submissionId: string,
): "community" | "project_anchor" {
  const overlay = originOverlayByArtifactSha().get(artifactSha256);
  return overlay?.submission_id === submissionId ? overlay.origin : "community";
}

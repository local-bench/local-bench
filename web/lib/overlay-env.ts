import { z } from "zod";
import overlayJson from "../community_env_overlay.json";

const SHA256_RE = /^[0-9a-f]{64}$/u;

const EnvOverlayEntrySchema = z.object({
  bundle_sha256: z.string().regex(SHA256_RE),
  hardware: z.object({
    gpu_name: z.string().nullable(),
    vram_gb: z.number().finite().nonnegative().nullable(),
  }).strict().readonly(),
  perf: z.object({
    decode_tps: z.number().finite().nonnegative().nullable(),
    tokens_to_answer_median: z.number().finite().nonnegative().nullable(),
    wall_time_seconds: z.number().finite().nonnegative().nullable(),
  }).strict().readonly(),
  source: z.literal("maintainer-backfill-from-bundle"),
}).strict().readonly();

const EnvOverlaySchema = z.record(z.string().regex(SHA256_RE), EnvOverlayEntrySchema).readonly();

export type CommunityEnvOverlayEntry = z.infer<typeof EnvOverlayEntrySchema>;

let cachedOverlay: ReadonlyMap<string, CommunityEnvOverlayEntry> | undefined;

export function envOverlayByArtifactSha(): ReadonlyMap<string, CommunityEnvOverlayEntry> {
  if (cachedOverlay !== undefined) return cachedOverlay;
  const parsed = EnvOverlaySchema.safeParse(overlayJson);
  cachedOverlay = parsed.success ? new Map(Object.entries(parsed.data)) : new Map();
  return cachedOverlay;
}

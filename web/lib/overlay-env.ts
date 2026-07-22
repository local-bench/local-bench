import { z } from "zod";
import overlayJson from "../community_env_overlay.json";

const SHA256_RE = /^[0-9a-f]{64}$/u;

const EnvOverlayEntrySchema = z.object({
  bundle_sha256: z.string().regex(SHA256_RE).optional(),
  hardware: z.object({
    gpu_name: z.string().nullable(),
    vram_gb: z.number().finite().nonnegative().nullable(),
  }).strict().readonly(),
  note: z.string().max(300).optional(),
  perf: z.object({
    decode_tps: z.number().finite().nonnegative().nullable(),
    overall_tps: z.number().finite().nonnegative().nullable().optional(),
    prefill_tps: z.number().finite().nonnegative().nullable().optional(),
    tokens_to_answer_median: z.number().finite().nonnegative().nullable(),
    wall_time_seconds: z.number().finite().nonnegative().nullable(),
  }).strict().readonly(),
  // Correction tier: unlike `perf` (backfill, loses to a submitted value), fields here
  // WIN over the submitted projection — for maintainer corrections of values that were
  // submitted wrong (e.g. a resumed run's wall clock recorded only its final segment).
  perf_overrides: z.object({
    wall_time_seconds: z.number().finite().nonnegative().optional(),
  }).strict().readonly().optional(),
  source: z.enum(["maintainer-backfill-from-bundle", "maintainer-backfill-from-run-doc"]),
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

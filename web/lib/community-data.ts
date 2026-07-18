import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";

const DATA_DIR = join(process.cwd(), "public", "data");
const UNSAFE_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;
const GROUP_ID_RE = /^community-group:[0-9a-f]{32}$/u;
const GROUP_SUFFIX_RE = /^[0-9a-f]{32}$/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;
const REVISION_RE = /^[0-9a-f]{40}$/u;
const REPO_ID_RE = /^[A-Za-z0-9_.\-]+\/[A-Za-z0-9_.\-]+$/u;

function safeText(maxCodePoints: number, minCodePoints = 0) {
  return z.string().refine(
    (value) => [...value].length >= minCodePoints && [...value].length <= maxCodePoints,
    `must contain ${minCodePoints}-${maxCodePoints} code points`,
  ).refine((value) => !UNSAFE_TEXT_RE.test(value), "contains unsafe text characters");
}

const ScoreSchema = z.number().finite().min(0).max(1);
const RepoIdSchema = safeText(200, 3).regex(REPO_ID_RE).brand("HuggingFaceRepoId");
const RevisionSchema = z.string().regex(REVISION_RE);
const ScoresSchema = z.object({
  composite_full: ScoreSchema.nullable().optional(),
  composite_static: ScoreSchema.nullable().optional(),
  headline_score: ScoreSchema.nullable().optional(),
  known_headline_contribution: ScoreSchema.optional(),
  measured_headline_weight: ScoreSchema.optional(),
  missing_headline_weight: ScoreSchema.optional(),
  n: z.number().int().nonnegative().optional(),
  partial_composite: ScoreSchema.optional(),
  partial_composite_scope: z.literal("measured_headline_axes").optional(),
  rank_scope: safeText(120, 1).optional(),
  static_index_version: safeText(120, 1).optional(),
}).strict().readonly();

const LineageEntrySchema = z.object({
  artifact_sha256: z.string().regex(SHA256_RE),
  association: z.object({
    artifact_to_repo: z.literal("unverified"),
    basis: z.literal("maintainer-associated"),
    note: safeText(200),
  }).strict().readonly(),
  card_declared_edges: z.array(z.object({
    base: RepoIdSchema,
    base_revision: RevisionSchema.nullable(),
    child: RepoIdSchema,
    child_revision: RevisionSchema,
    source: z.literal("hf-model-card"),
  }).strict().readonly()).readonly(),
  repo: z.object({
    id: RepoIdSchema,
    revision: RevisionSchema,
  }).strict().readonly(),
  resolution: z.object({
    resolved_at: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u)
      .refine((value) => !Number.isNaN(Date.parse(value))),
    status: z.enum(["complete", "truncated", "partial"]),
  }).strict().readonly(),
}).strict().readonly();

const CommunityVariantSchema = z.object({
  artifact_sha256: z.string().regex(SHA256_RE),
  display_name: safeText(120, 1).nullable(),
  lineage_enrichment: LineageEntrySchema.optional(),
  projection_object_sha256: z.string().regex(SHA256_RE),
  quant_label: safeText(32, 1).nullable(),
  ranked: z.literal(false),
  scores: ScoresSchema,
  submission_id: safeText(128, 1),
}).strict().readonly().refine(
  (variant) => variant.lineage_enrichment?.artifact_sha256 === undefined
    || variant.lineage_enrichment.artifact_sha256 === variant.artifact_sha256,
  "lineage artifact must match its variant",
);

const CommunityGroupSchema = z.object({
  community_model_group_id: z.string().regex(GROUP_ID_RE),
  identity_label: z.literal("community-declared, identity-unverified"),
  ranked: z.literal(false),
  schema_version: z.literal("localbench.community_publication.v2"),
  variants: z.array(CommunityVariantSchema).min(1).readonly(),
}).strict().readonly();

const CommunityIndexEntrySchema = z.object({
  community_model_group_id: z.string().regex(GROUP_ID_RE),
  group_path: z.string(),
  n_variants: z.number().int().nonnegative(),
}).strict().readonly().refine((entry) => {
  const suffix = entry.community_model_group_id.replace("community-group:", "");
  return entry.group_path === `community/groups/${suffix}.json`;
}, "community group path must match its id");

const CommunityIndexSchema = z.object({
  groups: z.array(CommunityIndexEntrySchema).readonly(),
  schema_version: z.literal("localbench.community_publication.v2"),
}).strict().readonly();

export type CommunityGroupData = z.infer<typeof CommunityGroupSchema>;
export type HuggingFaceRepoId = z.infer<typeof RepoIdSchema>;

export const COMMUNITY_GROUP_PLACEHOLDER_ID = "not-yet-published";

export function parseCommunityGroup(value: unknown): CommunityGroupData | null {
  const parsed = CommunityGroupSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function huggingFaceRepoUrl(repoId: HuggingFaceRepoId): string {
  const components = repoId.split("/", 2);
  const owner = components[0] ?? "";
  const name = components[1] ?? "";
  return `https://huggingface.co/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
}

async function readUnknown(segments: readonly string[]): Promise<unknown | null> {
  try {
    const parsed: unknown = JSON.parse(await readFile(join(DATA_DIR, ...segments), "utf8"));
    return parsed;
  } catch (error) {
    if (error instanceof Error) return null;
    throw error;
  }
}

async function readCommunityIndex(): Promise<z.infer<typeof CommunityIndexSchema> | null> {
  const parsed = CommunityIndexSchema.safeParse(await readUnknown(["community", "index.json"]));
  return parsed.success ? parsed.data : null;
}

export async function getCommunityGroup(groupId: string): Promise<CommunityGroupData | null> {
  if (!GROUP_SUFFIX_RE.test(groupId)) return null;
  return parseCommunityGroup(await readUnknown(["community", "groups", `${groupId}.json`]));
}

export async function getCommunityGroups(): Promise<readonly CommunityGroupData[] | null> {
  const index = await readCommunityIndex();
  if (index === null) return null;
  const groups: CommunityGroupData[] = [];
  for (const entry of index.groups) {
    const suffix = entry.community_model_group_id.replace("community-group:", "");
    const group = await getCommunityGroup(suffix);
    if (
      group === null
      || group.community_model_group_id !== entry.community_model_group_id
      || group.variants.length !== entry.n_variants
    ) return null;
    groups.push(group);
  }
  return groups;
}

export async function getCommunityGroupStaticParams(): Promise<readonly { readonly groupId: string }[]> {
  const index = await readCommunityIndex();
  if (index === null || index.groups.length === 0) {
    return [{ groupId: COMMUNITY_GROUP_PLACEHOLDER_ID }];
  }
  return index.groups.map((entry) => ({
    groupId: entry.community_model_group_id.replace("community-group:", ""),
  }));
}

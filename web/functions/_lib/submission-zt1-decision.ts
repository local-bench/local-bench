import { z } from "zod";
import { isRecord, parseJson } from "./submission-api-common";
import { ResultBundleSchema, type ResultBundle, type SubmissionApiEnv, type SubmissionRow } from "./submission-contracts";
import { readRawBundle } from "./submission-storage";

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const KnownArtifactsSchema = z.record(Sha256Schema, z.string().min(1));
const ProtectedPatternsSchema = z.array(z.string().min(1));

const FALLBACK_PROTECTED_PATTERNS = [
  "qwen",
  "gemma",
  "llama",
  "deepseek",
  "mistral",
  "phi",
  "gpt",
  "gemini",
  "claude",
] as const;

export type Zt1DecisionKind = "publishable" | "provisional" | "escalated";
export type Zt1IdentityClass = "known_artifact" | "unverified" | "protected";

export type Zt1DecisionPlan = {
  readonly boardDisplayLabel: string;
  readonly boardIdentityKey: string;
  readonly codingState: string;
  readonly details: Record<string, string | number | boolean | null>;
  readonly identityClass: Zt1IdentityClass;
  readonly provisionalReason: string | null;
  readonly provisionalUntil: string | null;
  readonly reason: string;
  readonly zt1Decision: Zt1DecisionKind;
};

type ModelMetadata = {
  readonly artifactHash: string | null;
  readonly displayName: string;
  readonly family: string | null;
  readonly fileSizeBytes: number | null;
};

type CodingState = "absent" | "verifier" | "generated_unverified" | "self_reported_exec";
type AgenticState = "absent" | "self_reported_agentic";

export async function zt1DecisionForAcceptedSubmission(
  env: SubmissionApiEnv,
  row: SubmissionRow,
): Promise<Zt1DecisionPlan> {
  const bundle = await acceptedBundle(env, row.raw_bundle_sha256);
  if (bundle === null) {
    return escalatedPlan("bundle_unavailable", unknownIdentity(), "absent", {});
  }
  const model = modelMetadata(bundle);
  const identity = resolveIdentity(env, row, model);
  const codingState = codingStateFor(row, bundle);
  const agenticState = agenticStateFor(bundle);
  const score = candidateScore(bundle);
  const details = {
    agentic_state: agenticState,
    coding_state: codingState,
    score,
  };
  if (!metadataSanitizes(model)) {
    return escalatedPlan("display_metadata_unsafe", identity, codingState, details);
  }
  if (row.duplicate_of !== null) {
    return escalatedPlan("duplicate_flag", identity, codingState, details);
  }
  const flags = await moderationFlags(env, row.submission_id);
  const blockingFlag = flags.find((flag) => flag !== "sybil_pattern");
  if (blockingFlag !== undefined) {
    return escalatedPlan(`${blockingFlag}_flag`, identity, codingState, details);
  }
  if (identity.identityClass === "protected") {
    return escalatedPlan("protected_identity", identity, codingState, details);
  }
  if (codingState === "self_reported_exec") {
    return escalatedPlan("coding_self_reported_exec", identity, codingState, details);
  }
  const impact = await highImpactReasons(env, row, model, score, identity.identityClass, agenticState);
  if (impact.reasons.length > 0) {
    const reason = impact.reasons.join(";");
    return {
      boardDisplayLabel: identity.boardDisplayLabel,
      boardIdentityKey: identity.boardIdentityKey,
      codingState,
      details: { ...details, impact_window_hours: impact.windowHours },
      identityClass: identity.identityClass,
      provisionalReason: reason,
      provisionalUntil: new Date(Date.now() + impact.windowHours * 60 * 60 * 1000).toISOString(),
      reason,
      zt1Decision: "provisional",
    };
  }
  return {
    boardDisplayLabel: identity.boardDisplayLabel,
    boardIdentityKey: identity.boardIdentityKey,
    codingState,
    details,
    identityClass: identity.identityClass,
    provisionalReason: null,
    provisionalUntil: null,
    reason: codingState === "generated_unverified" ? "auto_accept_coding_generated_unverified" : "publishable",
    zt1Decision: "publishable",
  };
}

async function acceptedBundle(env: SubmissionApiEnv, rawBundleSha256: string): Promise<ResultBundle | null> {
  const read = await readRawBundle(env, rawBundleSha256);
  if (read.kind !== "ok") {
    return null;
  }
  const parsed = parseJson(read.text);
  if (!isRecord(parsed)) {
    return null;
  }
  const bundle = ResultBundleSchema.safeParse(parsed);
  return bundle.success ? bundle.data : null;
}

function resolveIdentity(
  env: SubmissionApiEnv,
  row: SubmissionRow,
  model: ModelMetadata,
): {
  readonly boardDisplayLabel: string;
  readonly boardIdentityKey: string;
  readonly identityClass: Zt1IdentityClass;
} {
  if (model.artifactHash !== null) {
    const knownSlug = knownArtifacts(env)[model.artifactHash];
    if (typeof knownSlug === "string") {
      return {
        boardDisplayLabel: model.displayName,
        boardIdentityKey: knownSlug,
        identityClass: "known_artifact",
      };
    }
  }
  if (protectedIdentity(env, model)) {
    return {
      boardDisplayLabel: model.displayName,
      boardIdentityKey: model.artifactHash ?? "protected",
      identityClass: "protected",
    };
  }
  return {
    boardDisplayLabel: unverifiedDisplayLabel(row),
    boardIdentityKey: model.artifactHash ?? row.raw_bundle_sha256,
    identityClass: "unverified",
  };
}

function modelMetadata(bundle: ResultBundle): ModelMetadata {
  const manifest: Record<string, unknown> = isRecord(bundle.manifest) ? bundle.manifest : {};
  const manifestModel: Record<string, unknown> = isRecord(manifest["model"]) ? manifest["model"] : {};
  const model: Record<string, unknown> = isRecord(bundle.model) ? bundle.model : {};
  return {
    artifactHash: sha256OrNull(manifestModel["file_sha256"]),
    displayName: textOrDefault(model["name"], textOrDefault(manifestModel["family"], "community-declared model")),
    family: textOrNull(manifestModel["family"]),
    fileSizeBytes: numberOrNull(manifestModel["file_size_bytes"]),
  };
}

function metadataSanitizes(model: ModelMetadata): boolean {
  return [model.displayName, model.family ?? ""].every((value) => {
    if (value.length > 120) {
      return false;
    }
    const lower = value.toLowerCase();
    return !value.includes("<") && !value.includes(">") && !lower.includes("http://") && !lower.includes("https://") && !lower.includes("www.");
  });
}

function codingStateFor(row: SubmissionRow, bundle: ResultBundle): CodingState {
  const codingItems = bundle.items.filter((item) => isRecord(item) && item["bench"] === "bigcodebench_hard");
  if (codingItems.length === 0) {
    return "absent";
  }
  const sources = codingItems.map((item) => {
    if (!isRecord(item) || !isRecord(item["code_artifact"])) {
      return "missing";
    }
    const source = item["code_artifact"]["verdict_source"];
    return typeof source === "string" ? source : null;
  });
  if (sources.every((source) => source === "verifier")) {
    return "verifier";
  }
  if (row.origin === "community" && sources.every((source) => source === null)) {
    return "generated_unverified";
  }
  return "self_reported_exec";
}

function agenticStateFor(bundle: ResultBundle): AgenticState {
  return bundle.items.some((item) => isRecord(item) && item["bench"] === "appworld_c")
    ? "self_reported_agentic"
    : "absent";
}

async function highImpactReasons(
  env: SubmissionApiEnv,
  row: SubmissionRow,
  model: ModelMetadata,
  score: number | null,
  identityClass: Zt1IdentityClass,
  agenticState: AgenticState,
): Promise<{ readonly reasons: readonly string[]; readonly windowHours: 24 | 72 }> {
  const reasons: string[] = [];
  if (identityClass === "unverified") {
    reasons.push("unknown_identity");
  }
  if (agenticState === "self_reported_agentic") {
    reasons.push("self_reported_agentic");
  }
  if (score !== null) {
    const overall = await publicScores(env);
    const tenth = overall[9];
    if (overall.length >= 10 && tenth !== undefined && score > tenth.score) {
      reasons.push("top_10_overall");
    }
    const sizeClass = modelSizeClass(model.displayName, model.fileSizeBytes);
    if (sizeClass !== null) {
      const sizeScores = overall.filter((entry) => modelSizeClass(entry.displayName, null) === sizeClass);
      const third = sizeScores[2];
      if (sizeScores.length >= 3 && third !== undefined && score > third.score) {
        reasons.push("top_3_size_class");
      }
    }
    if (model.family !== null) {
      const familyScores = overall.filter((entry) => entry.family === model.family);
      const bestFamily = familyScores[0];
      if (bestFamily !== undefined && score > bestFamily.score) {
        reasons.push("family_number_one");
      }
    }
    const bestOverall = overall[0];
    if (bestOverall !== undefined && score - bestOverall.score > 1.5) {
      reasons.push("beats_prior_number_one");
    }
    const firstPageThreshold = overall[9] ?? overall[overall.length - 1];
    if (overall.length >= 9 && firstPageThreshold !== undefined && score > firstPageThreshold.score && await firstTimeSubmitter(env, row)) {
      reasons.push("first_page_first_time_key");
    }
  }
  const topImpact = reasons.some((reason) => !["first_page_first_time_key", "unknown_identity", "self_reported_agentic"].includes(reason));
  return { reasons, windowHours: topImpact ? 72 : 24 };
}

async function publicScores(env: SubmissionApiEnv): Promise<readonly { readonly displayName: string; readonly family: string | null; readonly score: number }[]> {
  const rows = await env.DB.prepare(
    `select model_display_name, model_family, coalesce(headline_score, partial_composite) as score
     from board_entries
     where visibility = 'public' and coalesce(headline_score, partial_composite) is not null
     order by coalesce(headline_score, partial_composite) desc`,
  ).all();
  return rows.results.flatMap((row) => {
    const score = numberOrNull(row["score"]);
    if (score === null) {
      return [];
    }
    return [{
      displayName: textOrDefault(row["model_display_name"], ""),
      family: textOrNull(row["model_family"]),
      score,
    }];
  });
}

async function firstTimeSubmitter(env: SubmissionApiEnv, row: SubmissionRow): Promise<boolean> {
  if (row.submitter_id === null) {
    return true;
  }
  const existing = await env.DB.prepare(
    `select count(*) as count
     from submissions
     where submitter_id = ? and submission_id <> ? and status = 'accepted' and publish_state in ('preview', 'published')`,
  )
    .bind(row.submitter_id, row.submission_id)
    .first();
  return numberOrNull(existing?.["count"]) === 0;
}

async function moderationFlags(env: SubmissionApiEnv, submissionId: string): Promise<readonly string[]> {
  try {
    const row = await env.DB.prepare("select zt1_flags_json from submissions where submission_id = ?")
      .bind(submissionId)
      .first();
    const parsed = parseJson(textOrDefault(row?.["zt1_flags_json"], "[]"));
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch (error) {
    if (missingZt1Column(error)) {
      return [];
    }
    throw error;
  }
}

function escalatedPlan(
  reason: string,
  identity: { readonly boardDisplayLabel: string; readonly boardIdentityKey: string; readonly identityClass: Zt1IdentityClass },
  codingState: string,
  details: Record<string, string | number | boolean | null>,
): Zt1DecisionPlan {
  return {
    boardDisplayLabel: identity.boardDisplayLabel,
    boardIdentityKey: identity.boardIdentityKey,
    codingState,
    details,
    identityClass: identity.identityClass,
    provisionalReason: null,
    provisionalUntil: null,
    reason,
    zt1Decision: "escalated",
  };
}

function unknownIdentity(): { readonly boardDisplayLabel: string; readonly boardIdentityKey: string; readonly identityClass: Zt1IdentityClass } {
  return { boardDisplayLabel: "community-declared · identity unverified", boardIdentityKey: "unknown", identityClass: "unverified" };
}

function knownArtifacts(env: SubmissionApiEnv): Record<string, string> {
  const parsed = jsonConfig(env.ZT1_KNOWN_ARTIFACTS_JSON, {});
  const result = KnownArtifactsSchema.safeParse(parsed);
  return result.success ? result.data : {};
}

function protectedIdentity(env: SubmissionApiEnv, model: ModelMetadata): boolean {
  const patterns = protectedPatterns(env);
  const haystack = `${model.displayName} ${model.family ?? ""}`.toLowerCase();
  return patterns.some((pattern) => haystack.includes(pattern.toLowerCase()));
}

function protectedPatterns(env: SubmissionApiEnv): readonly string[] {
  const parsed = jsonConfig(env.ZT1_PROTECTED_MODEL_PATTERNS_JSON, [...FALLBACK_PROTECTED_PATTERNS]);
  const result = ProtectedPatternsSchema.safeParse(parsed);
  return result.success ? result.data : FALLBACK_PROTECTED_PATTERNS;
}

function jsonConfig(raw: string | undefined, fallback: unknown): unknown {
  if (raw === undefined || raw.trim().length === 0) {
    return fallback;
  }
  const parsed = parseJson(raw);
  return parsed ?? fallback;
}

function unverifiedDisplayLabel(row: SubmissionRow): string {
  const credit = row.submitter_display_name ?? "community submitter";
  return `community-declared · identity unverified · ${credit}`;
}

function candidateScore(bundle: ResultBundle): number | null {
  const scores: Record<string, unknown> = isRecord(bundle.scores) ? bundle.scores : {};
  return numberOrNull(scores["headline_score"]) ?? numberOrNull(scores["partial_composite"]);
}

function modelSizeClass(displayName: string, fileSizeBytes: number | null): string | null {
  const match = /(\d+(?:\.\d+)?)\s*b\b/i.exec(displayName);
  if (match?.[1] !== undefined) {
    return `${Number(match[1]).toString().toLowerCase()}b`;
  }
  if (fileSizeBytes === null) {
    return null;
  }
  const approxBillions = Math.round(fileSizeBytes / 1_000_000_000);
  return approxBillions > 0 ? `${approxBillions}b` : null;
}

function textOrDefault(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function textOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sha256OrNull(value: unknown): string | null {
  const result = Sha256Schema.safeParse(value);
  return result.success ? result.data : null;
}

function missingZt1Column(error: unknown): boolean {
  return error instanceof Error && error.message.includes("zt1_flags_json");
}

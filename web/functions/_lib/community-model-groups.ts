import modelCatalog from "../../model_catalog.json";
import { CommunityModelGroupIdSchema, type SubmissionApiEnv } from "./submission-contracts";
import { jsonResponse } from "./submission-api-support";
import { clientIp } from "./submission-api-common";
import { rateLimited } from "./submission-rate-limit";

export const COMMUNITY_IDENTITY_LABEL = "community-declared, identity-unverified";
const catalogIdentities = new Set(modelCatalog.models.flatMap((model) => [model.id, model.slug]));

export function isDisjointCommunityGroupId(value: string): boolean {
  return CommunityModelGroupIdSchema.safeParse(value).success && !catalogIdentities.has(value);
}

export async function handleCreateCommunityModelGroup(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const body: unknown = await request.json();
  if (!isRecord(body) || typeof body["declared_model_name"] !== "string") {
    return jsonResponse(400, { code: "invalid_community_group", error: "declared_model_name is required" });
  }
  const declaredName = body["declared_model_name"].trim();
  if (declaredName.length < 1 || declaredName.length > 120 || /[<>]/.test(declaredName)) {
    return jsonResponse(400, { code: "invalid_community_group", error: "declared_model_name is invalid" });
  }
  const limit = await rateLimited(env, `community-groups:ip:${clientIp(request)}`, 10, 24 * 60 * 60);
  if (limit.limited) {
    return Response.json({ code: "rate_limited", retry_after_seconds: limit.retryAfterSeconds }, {
      headers: { "cache-control": "no-store", "retry-after": String(limit.retryAfterSeconds) },
      status: 429,
    });
  }
  const groupId = `community-group:${crypto.randomUUID().replaceAll("-", "")}`;
  if (!isDisjointCommunityGroupId(groupId)) throw new Error("community group namespace collision");
  await env.DB.prepare(
    "insert into community_model_groups (community_model_group_id, declared_model_name, identity_label) values (?, ?, ?)",
  ).bind(groupId, declaredName, COMMUNITY_IDENTITY_LABEL).run();
  return jsonResponse(201, { community_model_group_id: groupId, declared_model_name: declaredName, identity_label: COMMUNITY_IDENTITY_LABEL });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

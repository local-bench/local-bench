import { describe, expect, it } from "vitest";
import { COMMUNITY_IDENTITY_LABEL, handleCreateCommunityModelGroup, isDisjointCommunityGroupId } from "../functions/_lib/community-model-groups";
import { MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, createEnv, jsonRequest } from "./submission-test-support";
import { communityGroupBody, testKeyPair } from "./submission-contract-v2-support";

describe("server-issued community model groups", () => {
  it("issues an opaque namespace-disjoint identity with the mandatory label", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013] });
    const response = await handleCreateCommunityModelGroup(jsonRequest(
      "/api/community-model-groups",
      communityGroupBody("My two quant variants", testKeyPair()),
    ), env);
    const body = await response.json();
    expect(response.status).toBe(201);
    expect(body).toMatchObject({ identity_label: COMMUNITY_IDENTITY_LABEL });
    expect(body.community_model_group_id).toMatch(/^community-group:[0-9a-f]{32}$/);
    expect(isDisjointCommunityGroupId(body.community_model_group_id)).toBe(true);
    expect(isDisjointCommunityGroupId("gemma-4-12b-it")).toBe(false);
    expect(isDisjointCommunityGroupId("google/gemma-4-12b-it")).toBe(false);
  });

  it("requires proof of possession before creating a group", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013] });
    const response = await handleCreateCommunityModelGroup(jsonRequest(
      "/api/community-model-groups",
      { declared_model_name: "Fixture unsigned group" },
    ), env);
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "pop_invalid" });
  });

  it.each([
    `community-group:${"a".repeat(31)}`,
    `community-group:${"a".repeat(32)}suffix`,
    `community-group:${"a".repeat(31)}z`,
  ])("rejects malformed ids at the SQL constraint: %s", async (groupId) => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013] });
    await expect(env.DB.prepare(
      "insert into community_model_groups (community_model_group_id, declared_model_name) values (?, 'invalid')",
    ).bind(groupId).run()).rejects.toThrow();
  });
});

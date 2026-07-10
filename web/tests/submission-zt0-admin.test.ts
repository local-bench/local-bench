import { describe, expect, it } from "vitest";
import { onRequestPost as gcSubmissions } from "../functions/api/admin/gc";
import { onRequestGet as getOpsSettings, onRequestPost as postOpsSettings } from "../functions/api/admin/ops-settings";
import { onRequestPost as suppressSubmission } from "../functions/api/admin/submissions/[submissionId]/suppress";
import { onRequestPost as withdrawSubmission } from "../functions/api/admin/submissions/[submissionId]/withdraw";
import {
  acceptedSubmission,
  adminEmptyPost,
  adminGet,
  adminJson,
  createZt0Env,
  expectSubmissionRow,
  expectTransition,
  insertSubmission,
} from "./submission-zt0-support";
import {
  issueEnvelope,
  jsonRequest,
  tableExists,
} from "./submission-test-support";

describe("ZT-0 admin operations", () => {
  it("creates the additive transition and ops settings tables", async () => {
    // Given: the contract-v2 submissions schema is already present.
    const env = await createZt0Env();

    // When / Then: 0006 adds only the new ZT-0 tables and seeds the kill switch off.
    expect(await tableExists(env.DB, "submission_transitions")).toBe(true);
    expect(await tableExists(env.DB, "ops_settings")).toBe(true);
    const setting = await env.DB.prepare("select key, value, disabled_by from ops_settings where key = 'auto_publish'").first();
    expect(setting).toEqual({ disabled_by: null, key: "auto_publish", value: "off" });
  });

  it("requires admin auth for suppress and withdraw", async () => {
    // Given: an accepted submission exists.
    const env = await createZt0Env();
    const submissionId = await acceptedSubmission(env, { publishState: "published" });

    // When: the suppress endpoint is called without the admin secret.
    const response = await suppressSubmission({
      env,
      params: { submissionId },
      request: jsonRequest(`/api/admin/submissions/${submissionId}/suppress`, { reason: "abuse report" }),
    });

    // Then: the existing admin-secret auth contract blocks it.
    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({ code: "unauthorized" });
  });

  it("suppresses accepted rows and forces publish_state hidden atomically", async () => {
    // Given: an accepted submission is visible in publication state.
    const env = await createZt0Env();
    const submissionId = await acceptedSubmission(env, { publishState: "published" });

    // When: a maintainer suppresses it with a required reason.
    const response = await suppressSubmission({
      env,
      params: { submissionId },
      request: adminJson(`/api/admin/submissions/${submissionId}/suppress`, { reason: "integrity issue" }),
    });

    // Then: status and publication visibility change together, and a transition is recorded.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ publish_state: "hidden", status: "suppressed" });
    await expectSubmissionRow(env, submissionId, { publish_state: "hidden", status: "suppressed" });
    await expectTransition(env, submissionId, {
      actor: "maintainer",
      from_status: "accepted",
      publish_state: "hidden",
      reason: "integrity issue",
      to_status: "suppressed",
    });
  });

  it("withdraws accepted rows and rejects terminal operations from the wrong state", async () => {
    // Given: one accepted row and one still-ticketed row.
    const env = await createZt0Env();
    const acceptedId = await acceptedSubmission(env, { publishState: "preview" });
    const ticket = await issueEnvelope(env, `${"c".repeat(64)}`);

    // When: the accepted row is withdrawn and the ticketed row is withdrawn.
    const ok = await withdrawSubmission({
      env,
      params: { submissionId: acceptedId },
      request: adminJson(`/api/admin/submissions/${acceptedId}/withdraw`, { reason: "submitter requested removal" }),
    });
    const conflict = await withdrawSubmission({
      env,
      params: { submissionId: ticket.ticket_id },
      request: adminJson(`/api/admin/submissions/${ticket.ticket_id}/withdraw`, { reason: "not accepted yet" }),
    });

    // Then: only accepted -> withdrawn is legal.
    expect(ok.status).toBe(200);
    expect(await ok.json()).toMatchObject({ publish_state: "hidden", status: "withdrawn" });
    expect(conflict.status).toBe(409);
    expect(await conflict.json()).toMatchObject({ code: "invalid_transition" });
  });

  it("enforces the auto_publish kill-switch one-way owner rule", async () => {
    // Given: the default ops setting exists.
    const env = await createZt0Env();

    // When / Then: agents can disable, but cannot re-enable after an owner disable.
    const agentOff = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "agent", key: "auto_publish", value: "off" }),
    });
    expect(agentOff.status).toBe(200);
    expect(await agentOff.json()).toMatchObject({ disabled_by: "agent", key: "auto_publish", value: "off" });

    const ownerOff = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "owner", key: "auto_publish", value: "off" }),
    });
    expect(ownerOff.status).toBe(200);

    const agentOn = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "agent", key: "auto_publish", value: "on" }),
    });
    expect(agentOn.status).toBe(403);
    expect(await agentOn.json()).toMatchObject({ code: "kill_switch_owner_only" });

    const securityOff = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "security", key: "auto_publish", value: "off" }),
    });
    expect(securityOff.status).toBe(200);

    const agentOnAfterSecurity = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "agent", key: "auto_publish", value: "on" }),
    });
    expect(agentOnAfterSecurity.status).toBe(200);
    expect(await agentOnAfterSecurity.json()).toMatchObject({ disabled_by: null, key: "auto_publish", value: "on" });

    const ownerOn = await postOpsSettings({
      env,
      request: adminJson("/api/admin/ops-settings", { actor: "owner", key: "auto_publish", value: "on" }),
    });
    expect(ownerOn.status).toBe(200);
    expect(await ownerOn.json()).toMatchObject({ disabled_by: null, key: "auto_publish", value: "on" });

    const listed = await getOpsSettings({ env, request: adminGet("/api/admin/ops-settings") });
    expect(listed.status).toBe(200);
    expect(await listed.json()).toMatchObject({ settings: [expect.objectContaining({ key: "auto_publish" })] });
  });

  it("reports and applies garbage collection policies without deleting projections", async () => {
    // Given: rows matching every ZT-0 GC policy and raw objects in R2.
    const env = await createZt0Env();
    await insertSubmission(env, {
      id: "ticket-old",
      rawSha: `${"1".repeat(64)}`,
      status: "ticketed",
      expiresAt: "2000-01-01T00:00:00Z",
    });
    await insertSubmission(env, {
      id: "rejected-old",
      rawKey: "submissions/raw/rejected-old.json",
      rawSha: `${"2".repeat(64)}`,
      status: "rejected",
      validatedAt: "2000-01-01T00:00:00Z",
    });
    await insertSubmission(env, {
      id: "accepted-old",
      projectionKey: "projections/accepted-old/projection.json",
      rawKey: "submissions/raw/accepted-old.json",
      rawSha: `${"3".repeat(64)}`,
      status: "accepted",
      uploadedAt: "2000-01-01T00:00:00Z",
    });
    await insertSubmission(env, {
      id: "pending-old",
      rawKey: "submissions/raw/pending-old.json",
      rawSha: `${"4".repeat(64)}`,
      status: "pending_verification",
      uploadedAt: "2000-01-01T00:00:00Z",
    });
    await env.SUBMISSIONS.put("submissions/raw/rejected-old.json", "raw rejected");
    await env.SUBMISSIONS.put("submissions/raw/accepted-old.json", "raw accepted");
    await env.SUBMISSIONS.put("submissions/raw/pending-old.json", "raw pending");
    await env.SUBMISSIONS.put("projections/accepted-old/projection.json", "projection");

    // When: GC is first dry-run and then applied.
    const dryRun = await gcSubmissions({ env, request: adminJson("/api/admin/gc", { apply: false }) });
    const applied = await gcSubmissions({ env, request: adminJson("/api/admin/gc", { apply: true }) });

    // Then: dry-run reports only, apply performs the status/null/delete actions.
    expect(dryRun.status).toBe(200);
    expect(await dryRun.json()).toMatchObject({
      apply: false,
      accepted_raw_deleted: { count: 1, submission_ids: ["accepted-old"] },
      expired_tickets: { count: 1, submission_ids: ["ticket-old"] },
      rejected_raw_deleted: { count: 1, submission_ids: ["rejected-old"] },
      stale_pending_expired: { count: 1, submission_ids: ["pending-old"] },
    });
    expect(applied.status).toBe(200);
    await expectSubmissionRow(env, "ticket-old", { status: "expired" });
    await expectSubmissionRow(env, "rejected-old", { raw_bundle_r2_key: null, status: "rejected" });
    await expectSubmissionRow(env, "accepted-old", { raw_bundle_r2_key: null, status: "accepted" });
    await expectSubmissionRow(env, "pending-old", { raw_bundle_r2_key: null, status: "expired" });
    expect(await env.SUBMISSIONS.get("submissions/raw/rejected-old.json")).toBeNull();
    expect(await env.SUBMISSIONS.get("submissions/raw/accepted-old.json")).toBeNull();
    expect(await env.SUBMISSIONS.get("submissions/raw/pending-old.json")).toBeNull();
    expect(await env.SUBMISSIONS.get("projections/accepted-old/projection.json")).not.toBeNull();
    await expectTransition(env, "ticket-old", { actor: "gc", from_status: "ticketed", to_status: "expired" });
    await expectTransition(env, "accepted-old", { actor: "gc", from_status: "accepted", to_status: "accepted" });
  });

  it("defaults GC to dry-run when the body is omitted", async () => {
    // Given: the maintainer calls the admin GC endpoint without a JSON body.
    const env = await createZt0Env();

    // When: no body is sent.
    const response = await gcSubmissions({ env, request: adminEmptyPost("/api/admin/gc") });

    // Then: the request is accepted as a no-op dry run.
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      accepted_raw_deleted: { count: 0, submission_ids: [] },
      apply: false,
      expired_tickets: { count: 0, submission_ids: [] },
      rejected_raw_deleted: { count: 0, submission_ids: [] },
    });
  });
});

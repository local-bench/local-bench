import { describe, expect, it } from "vitest";
import { onRequestGet as downloadBundle } from "../functions/api/admin/submissions/[submissionId]/bundle";
import { onRequestPost as updateDisplayName } from "../functions/api/admin/submissions/[submissionId]/display-name";
import { onRequestGet as listAdminSubmissions } from "../functions/api/admin/submissions";
import {
  ADMIN_SECRET,
  RAW_BUNDLE_SHA,
  RESULT_BUNDLE_JSON,
  createEnv,
  getRequest,
  issueEnvelope,
  jsonRequest,
} from "./submission-test-support";

const VALIDATOR_SECRET = "fixture-validator-secret";

describe("publish-then-moderate admin APIs", () => {
  it("allows the validator credential on the submissions list", async () => {
    const base = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const env = { ...base, VALIDATOR_API_SECRET: VALIDATOR_SECRET };
    const response = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions", {
        "x-localbench-validator-secret": VALIDATOR_SECRET,
      }),
    });
    expect(response.status).toBe(200);
  });

  it("streams a raw bundle to admin and validator credentials", async () => {
    const base = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const env = { ...base, VALIDATOR_API_SECRET: VALIDATOR_SECRET };
    const envelope = await issueEnvelope(env);
    await env.SUBMISSIONS.put(`submissions/raw/${RAW_BUNDLE_SHA}.json`, RESULT_BUNDLE_JSON);

    for (const headers of [
      { "x-localbench-admin-secret": ADMIN_SECRET },
      { "x-localbench-validator-secret": VALIDATOR_SECRET },
    ]) {
      const response = await downloadBundle({
        env,
        params: { submissionId: envelope.ticket_id },
        request: getRequest(`/api/admin/submissions/${envelope.ticket_id}/bundle`, headers),
      });
      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toBe("application/octet-stream");
      expect(response.headers.get("content-disposition")).toBe(
        `attachment; filename="localbench-bundle-${RAW_BUNDLE_SHA}.json"`,
      );
      expect(await response.text()).toBe(RESULT_BUNDLE_JSON);
    }
  });

  it("returns 404 when the raw bundle object is missing", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const response = await downloadBundle({
      env,
      params: { submissionId: envelope.ticket_id },
      request: getRequest(`/api/admin/submissions/${envelope.ticket_id}/bundle`, {
        "x-localbench-admin-secret": ADMIN_SECRET,
      }),
    });
    expect(response.status).toBe(404);
  });

  it("validates, persists, and audits an admin display-name backfill", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const envelope = await issueEnvelope(env);
    const invalid = await updateDisplayName({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/admin/submissions/${envelope.ticket_id}/display-name`, {
        display_name: "bad/name",
      }, { "x-localbench-admin-secret": ADMIN_SECRET }),
    });
    const valid = await updateDisplayName({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/admin/submissions/${envelope.ticket_id}/display-name`, {
        display_name: "Fixture Submitter",
      }, { "x-localbench-admin-secret": ADMIN_SECRET }),
    });
    const row = await env.DB.prepare("select submitter_display_name from submissions where submission_id = ?")
      .bind(envelope.ticket_id).first();
    const audit = await env.DB.prepare(
      "select actor, reason from submission_transitions where submission_id = ? order by id desc limit 1",
    ).bind(envelope.ticket_id).first();

    expect(invalid.status).toBe(400);
    expect(valid.status).toBe(200);
    expect(row).toMatchObject({ submitter_display_name: "Fixture Submitter" });
    expect(audit).toMatchObject({ actor: "maintainer", reason: "submitter display name updated" });
  });

  it("does not authorize validator credentials for display-name changes", async () => {
    const base = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const env = { ...base, VALIDATOR_API_SECRET: VALIDATOR_SECRET };
    const envelope = await issueEnvelope(env);
    const response = await updateDisplayName({
      env,
      params: { submissionId: envelope.ticket_id },
      request: jsonRequest(`/api/admin/submissions/${envelope.ticket_id}/display-name`, {
        display_name: "Fixture Submitter",
      }, { "x-localbench-validator-secret": VALIDATOR_SECRET }),
    });
    expect(response.status).toBe(401);
  });

  it("rejects validator authentication when its secret is not configured", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const response = await listAdminSubmissions({
      env,
      request: getRequest("/api/admin/submissions", {
        "x-localbench-validator-secret": VALIDATOR_SECRET,
      }),
    });
    expect(response.status).toBe(503);
  });
});

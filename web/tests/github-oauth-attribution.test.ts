import { describe, expect, it } from "vitest";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { ADMIN_SECRET, createEnv, jsonRequest } from "./submission-test-support";
import {
  TEST_IP,
  communityTicketBody,
  testKeyPair,
} from "./submission-contract-v2-support";

describe("GitHub account submission attribution", () => {
  it("stamps bound keys while preserving null attribution for 0.4.2 keys", async () => {
    // Given: one Ed25519 key is bound to a GitHub account and another remains key-only.
    // Attribution resolution is a flag-on feature, so enable it for this case.
    const env = { ...(await createEnv({ includeAdminSecret: true, includeR2Secrets: true })), GITHUB_OAUTH_ENABLED: "on" };
    const boundKey = testKeyPair();
    const unboundKey = testKeyPair();
    const accountId = `acct_${"a".repeat(32)}`;
    await env.DB.prepare("insert into accounts (account_id, github_user_id, github_login) values (?, ?, ?)")
      .bind(accountId, "7654321", "bound-user")
      .run();
    await env.DB.prepare(
      "insert into account_keys (public_key_hex, account_id, binding_signature) values (?, ?, ?)",
    ).bind(boundKey.publicKeyHex, accountId, "f".repeat(128)).run();

    // When: both clients issue otherwise identical community tickets.
    const boundResponse = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        communityTicketBody("b".repeat(64), boundKey),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });
    const unboundResponse = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        communityTicketBody("c".repeat(64), unboundKey),
        { "CF-Connecting-IP": TEST_IP },
      ),
    });

    // Then: only the bound key stamps immutable account attribution on its submission row.
    expect(boundResponse.status).toBe(201);
    expect(unboundResponse.status).toBe(201);
    const bound = await env.DB.prepare(
      "select account_id, github_login from submissions where raw_bundle_sha256 = ?",
    ).bind("b".repeat(64)).first();
    const unbound = await env.DB.prepare(
      "select account_id, github_login from submissions where raw_bundle_sha256 = ?",
    ).bind("c".repeat(64)).first();
    expect(bound).toMatchObject({ account_id: accountId, github_login: "bound-user" });
    expect(unbound).toMatchObject({ account_id: null, github_login: null });
  });
});


describe("GitHub attribution security gates (red-team follow-ups)", () => {
  it("does not resolve attribution when the OAuth flag is off (bound key stamps null)", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
    const boundKey = testKeyPair();
    const accountId = `acct_${"d".repeat(32)}`;
    await env.DB.prepare("insert into accounts (account_id, github_user_id, github_login) values (?, ?, ?)")
      .bind(accountId, "9990001", "flag-off-user").run();
    await env.DB.prepare("insert into account_keys (public_key_hex, account_id, binding_signature) values (?, ?, ?)")
      .bind(boundKey.publicKeyHex, accountId, "f".repeat(128)).run();

    const response = await issueTicket({
      env,
      request: jsonRequest("/api/submissions/tickets", communityTicketBody("e".repeat(64), boundKey), { "CF-Connecting-IP": TEST_IP }),
    });
    expect(response.status).toBe(201);
    const row = await env.DB.prepare("select account_id, github_login from submissions where raw_bundle_sha256 = ?")
      .bind("e".repeat(64)).first();
    expect(row).toMatchObject({ account_id: null, github_login: null });
  });

  it("admin (project_anchor) path cannot stamp a victim's bound key without PoP", async () => {
    const env = { ...(await createEnv({ includeAdminSecret: true, includeR2Secrets: true })), GITHUB_OAUTH_ENABLED: "on" };
    const victimKey = testKeyPair();
    const accountId = `acct_${"e".repeat(32)}`;
    await env.DB.prepare("insert into accounts (account_id, github_user_id, github_login) values (?, ?, ?)")
      .bind(accountId, "5550002", "victim-user").run();
    await env.DB.prepare("insert into account_keys (public_key_hex, account_id, binding_signature) values (?, ?, ?)")
      .bind(victimKey.publicKeyHex, accountId, "f".repeat(128)).run();

    // Admin-authenticated ticket supplying the victim's public_key but no community PoP.
    const response = await issueTicket({
      env,
      request: jsonRequest(
        "/api/submissions/tickets",
        { accepted_suite_terms: true, bundle_sha256: "f".repeat(64), public_key: victimKey.publicKeyHex, submitter_id: "attacker-anchor", expected_suite_release_id: null, expected_suite_manifest_sha256: null },
        { "CF-Connecting-IP": TEST_IP, "x-localbench-admin-secret": ADMIN_SECRET },
      ),
    });
    expect(response.status).toBe(201);
    const row = await env.DB.prepare("select origin, account_id, github_login from submissions where raw_bundle_sha256 = ?")
      .bind("f".repeat(64)).first();
    expect(row).toMatchObject({ origin: "project_anchor", account_id: null, github_login: null });
  });
});

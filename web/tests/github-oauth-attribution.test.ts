import { describe, expect, it } from "vitest";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { createEnv, jsonRequest } from "./submission-test-support";
import {
  TEST_IP,
  communityTicketBody,
  testKeyPair,
} from "./submission-contract-v2-support";

describe("GitHub account submission attribution", () => {
  it("stamps bound keys while preserving null attribution for 0.4.2 keys", async () => {
    // Given: one Ed25519 key is bound to a GitHub account and another remains key-only.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true });
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

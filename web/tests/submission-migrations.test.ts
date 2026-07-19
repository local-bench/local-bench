import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  MIGRATION_0001,
  MIGRATION_0002,
  MIGRATION_0003,
  MIGRATION_0004,
  MIGRATION_0005,
  MIGRATION_0006,
  MIGRATION_0007,
  MIGRATION_0008,
  MIGRATION_0009,
  MIGRATION_0010,
  MIGRATION_0011,
  MIGRATION_0012,
  MIGRATION_0013,
  MIGRATION_0014,
  MIGRATION_0015,
  MIGRATION_0016,
  MIGRATION_0017,
  MIGRATION_0018,
  applyMigration,
  columnCount,
  createEnv,
  indexExists,
  tableExists,
} from "./submission-test-support";

describe("submission D1 migrations", () => {
  it("adds GitHub accounts, opaque OAuth handles, and submission attribution columns", async () => {
    // Given: Track D's append-only migration is expected after the existing schema.
    const migrationUrl = new URL("../migrations/0015_accounts.sql", import.meta.url);
    expect(existsSync(migrationUrl)).toBe(true);
    const migration = readFileSync(migrationUrl, "utf-8");
    const env = await createEnv({
      includeAdminSecret: true,
      includeR2Secrets: true,
      migrations: [
        MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0009,
        MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014,
      ],
    });

    // When: migration 0015 is applied to the current D1 schema.
    await applyMigration(env.DB, migration);

    // Then: account binding and single-use OAuth state have dedicated storage.
    expect(await tableExists(env.DB, "accounts")).toBe(true);
    expect(await tableExists(env.DB, "account_keys")).toBe(true);
    expect(await tableExists(env.DB, "github_oauth_device_codes")).toBe(true);
    expect(await tableExists(env.DB, "github_oauth_states")).toBe(true);
    expect(await columnCount(env.DB, "submissions", "account_id")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "github_login")).toBe(1);
  });

  it("reconciles historical migrations through the contract-v2 schema", async () => {
    // Given: a fresh D1 database applies the historical 0001 schema before the incompatible 0002.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    await applyMigration(env.DB, MIGRATION_0001);
    const migration0002Errors = await applyMigration(env.DB, MIGRATION_0002, { allowErrors: true });

    // When: the reconcile migration is applied after the recorded 0002 publish_state-index conflict.
    await applyMigration(env.DB, MIGRATION_0003);
    await applyMigration(env.DB, MIGRATION_0004);

    // Then: the database has the contract-v2 table shape and the dead 0001 tables are gone.
    expect(migration0002Errors.some((error) => error.message.includes("publish_state"))).toBe(true);
    expect(await columnCount(env.DB, "submissions", "tier")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "raw_bundle_r2_key")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "expires_at")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "run_payload_sha256")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "duplicate_of")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "r2_key")).toBe(0);
    expect(await indexExists(env.DB, "submissions_publish_state_idx")).toBe(true);
    expect(await indexExists(env.DB, "submissions_raw_bundle_sha256_uq")).toBe(true);
    expect(await indexExists(env.DB, "submissions_ticket_id_uq")).toBe(true);
    expect(await indexExists(env.DB, "submissions_run_payload_sha_idx")).toBe(true);
    expect(await tableExists(env.DB, "rate_counters")).toBe(true);
    expect(await tableExists(env.DB, "verification_jobs")).toBe(false);
    expect(await tableExists(env.DB, "admin_decisions")).toBe(false);
    expect(await tableExists(env.DB, "suites")).toBe(false);
    expect(await tableExists(env.DB, "board_entries")).toBe(true);
  });

  it("adds the public queue model label without exposing bundle contents", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    await applyMigration(env.DB, MIGRATION_0002);
    await applyMigration(env.DB, MIGRATION_0004);

    await applyMigration(env.DB, MIGRATION_0009);

    expect(await columnCount(env.DB, "submissions", "declared_model_slug")).toBe(1);
  });

  it("applies the complete migration sequence with the custom Wrangler-ledger simulator", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    const migrations = [
      ["0002_submission_slice_index.sql", MIGRATION_0002],
      ["0003_submission_reconcile.sql", MIGRATION_0003],
      ["0004_submission_contract_v2.sql", MIGRATION_0004],
      ["0005_submitter_display_name.sql", MIGRATION_0005],
      ["0006_zt0_foundation.sql", MIGRATION_0006],
      ["0007_feedback.sql", MIGRATION_0007],
      ["0008_zt1_zero_touch.sql", MIGRATION_0008],
      ["0009_pending_verification_queue.sql", MIGRATION_0009],
      ["0010_submission_admission_security.sql", MIGRATION_0010],
      ["0011_publication_snapshots.sql", MIGRATION_0011],
      ["0012_maintainer_attestations.sql", MIGRATION_0012],
      ["0013_community_model_groups.sql", MIGRATION_0013],
      ["0014_projection_storage_fences.sql", MIGRATION_0014],
      ["0015_accounts.sql", MIGRATION_0015],
      ["0016_client_reported_projection.sql", MIGRATION_0016],
      ["0017_submission_upload_security.sql", MIGRATION_0017],
      ["0018_repair_maintainer_attestation_fk.sql", MIGRATION_0018],
    ] as const;

    await applyWithWranglerLedger(env.DB, migrations);
    await applyWithWranglerLedger(env.DB, migrations);

    expect(await columnCount(env.DB, "submissions", "declared_model_slug")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "submitter_display_name")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "zt1_decision")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "state_revision")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "projection_object_sha256")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "upload_declared_size_bytes")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "upload_target_url")).toBe(1);
    expect(await tableExists(env.DB, "publication_snapshots")).toBe(true);
    expect(await tableExists(env.DB, "maintainer_verification_attestations")).toBe(true);
    expect(await tableExists(env.DB, "community_model_groups")).toBe(true);
    expect(await tableExists(env.DB, "projection_storage_fences")).toBe(true);
    expect(await tableExists(env.DB, "accounts")).toBe(true);
    const applied = await env.DB.prepare("select count(*) as count from d1_migrations").first();
    expect(applied?.["count"]).toBe(17);
  }, 15_000);

  it("relaxes verification_level without losing legacy rows", async () => {
    // Given: the pre-reset schema contains a suppressed legacy row using an old verification value.
    const env = await createEnv({
      includeAdminSecret: true,
      includeR2Secrets: true,
      migrations: [
        MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008,
        MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012, MIGRATION_0013,
        MIGRATION_0014, MIGRATION_0015,
      ],
    });
    const legacySha = "d".repeat(64);
    await env.DB.prepare(
      `insert into submissions (
        submission_id, origin, status, status_reason, raw_bundle_sha256, idempotency_key,
        verification_level, publish_state
      ) values ('legacy_suppressed', 'community', 'suppressed', 'legacy evidence', ?, ?, 'bundle_rescored', 'hidden')`,
    ).bind(legacySha, legacySha).run();

    // When: the additive relaxation migration is applied.
    await applyMigration(env.DB, MIGRATION_0016);
    await env.DB.prepare("update submissions set verification_level = 'client_reported' where submission_id = 'legacy_suppressed'").run();

    // Then: the legacy row and suppression state survive while the new value is accepted.
    const row = await env.DB.prepare(
      "select submission_id, status, status_reason, verification_level from submissions where submission_id = 'legacy_suppressed'",
    ).first();
    expect(row).toMatchObject({
      status: "suppressed",
      status_reason: "legacy evidence",
      submission_id: "legacy_suppressed",
      verification_level: "client_reported",
    });
  });

  it("replays 0001 through 0018 with foreign keys enabled and repairs attestation bindings", async () => {
    // Given: the production migration sequence starts from 0001 with SQLite FK enforcement enabled.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    await env.DB.prepare("pragma foreign_keys = on").run();
    await applyMigration(env.DB, MIGRATION_0001);
    await applyMigration(env.DB, MIGRATION_0002, { allowErrors: true });

    // When: every reconcile and additive migration through the repair is applied in order.
    for (const migration of [
      MIGRATION_0003, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0007,
      MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0012,
      MIGRATION_0013, MIGRATION_0014, MIGRATION_0015, MIGRATION_0016, MIGRATION_0017,
      MIGRATION_0018,
    ]) {
      await applyMigration(env.DB, migration);
    }

    // Then: the live attestation table references submissions and the database has no FK violations.
    const foreignKeys = await env.DB.prepare(
      "select \"table\" as target_table from pragma_foreign_key_list('maintainer_verification_attestations')",
    ).all();
    const violations = await env.DB.prepare("pragma foreign_key_check").all();
    expect(foreignKeys.results).toContainEqual({ target_table: "submissions" });
    expect(violations.results).toEqual([]);
  }, 15_000);
});

async function applyWithWranglerLedger(
  db: import("../functions/_lib/submission-contracts").D1DatabaseBinding,
  migrations: readonly (readonly [string, string])[],
): Promise<void> {
  await db.prepare(
    "create table if not exists d1_migrations (id integer primary key autoincrement, name text not null unique, applied_at text not null default (datetime('now')))",
  ).run();
  for (const [name, sql] of migrations) {
    const recorded = await db.prepare("select name from d1_migrations where name = ?").bind(name).first();
    if (recorded !== null) continue;
    await applyMigration(db, sql);
    await db.prepare("insert into d1_migrations (name) values (?)").bind(name).run();
  }
}

import { describe, expect, it } from "vitest";
import {
  MIGRATION_0001,
  MIGRATION_0002,
  MIGRATION_0003,
  applyMigration,
  columnCount,
  createEnv,
  indexExists,
  tableExists,
} from "./submission-test-support";

describe("submission D1 migrations", () => {
  it("reconciles 0001 then 0002 fresh-DB drift through the 0003 migration", async () => {
    // Given: a fresh D1 database applies the historical 0001 schema before the incompatible 0002.
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: [] });
    await applyMigration(env.DB, MIGRATION_0001);
    const migration0002Errors = await applyMigration(env.DB, MIGRATION_0002, { allowErrors: true });

    // When: the reconcile migration is applied after the recorded 0002 publish_state-index conflict.
    await applyMigration(env.DB, MIGRATION_0003);

    // Then: the database has the 0002 table shape and the dead 0001 tables are gone.
    expect(migration0002Errors.some((error) => error.message.includes("publish_state"))).toBe(true);
    expect(await columnCount(env.DB, "submissions", "tier")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "raw_bundle_r2_key")).toBe(1);
    expect(await columnCount(env.DB, "submissions", "r2_key")).toBe(0);
    expect(await indexExists(env.DB, "submissions_publish_state_idx")).toBe(true);
    expect(await tableExists(env.DB, "verification_jobs")).toBe(false);
    expect(await tableExists(env.DB, "admin_decisions")).toBe(false);
    expect(await tableExists(env.DB, "suites")).toBe(false);
    expect(await tableExists(env.DB, "board_entries")).toBe(true);
  });
});

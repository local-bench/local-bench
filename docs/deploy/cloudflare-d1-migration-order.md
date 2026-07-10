# Cloudflare D1 migration-before-code order

Submission Worker code must never be deployed before the D1 schema it reads and writes. In particular, code after the bridge hardening requires `0009_pending_verification_queue.sql` and `0010_submission_admission_security.sql`.

For every Cloudflare release:

1. Build and test the exact revision locally.
2. Apply remote D1 migrations with Wrangler and wait for a successful ledger entry for every new file.
3. Inspect the remote migration list and confirm `0009`/`0010` (or the release's newest migration) are recorded.
4. Only then deploy the Pages/Worker code from that same revision.
5. Smoke the ticket, status, queue, and admin-list reads. Do not create a production upload as a smoke test unless it is part of an approved canary.

Wrangler's `d1_migrations` ledger is the replay guard. The migrations contain ordinary SQLite `ALTER TABLE ... ADD COLUMN` statements because the D1 SQLite grammar used by this project does not accept a portable guarded add-column form. Do not replay migration SQL directly: rerun the Wrangler migration command, which skips names already present in its ledger.

If code was deployed first, roll the code back immediately, apply the missing migrations, verify the ledger, and then redeploy. Do not attempt to make the live code tolerate a half-migrated schema.

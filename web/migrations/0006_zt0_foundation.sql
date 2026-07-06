-- 0006: ZT-0 moderation foundation.
--
-- Part 1 — relax the submissions.status CHECK. The typed state machine (submission-state.ts)
-- adds lifecycle states ('withdrawn', 'suppressed', 'expired') that the enum CHECK baked into
-- the table by 0004 would reject IN PRODUCTION. SQLite cannot drop a CHECK constraint, so this
-- rebuilds the table exactly as 0004 + 0005 left it, with status relaxed to plain
-- `text not null` (transition legality is enforced in code, single source of truth). The
-- earlier migrations stay byte-identical — editing an already-applied migration only changes
-- fresh databases and silently diverges from the deployed one.

drop index if exists submissions_status_idx;
drop index if exists submissions_publish_state_idx;
drop index if exists submissions_raw_bundle_sha256_uq;
drop index if exists submissions_ticket_id_uq;
drop index if exists submissions_run_payload_sha_idx;
drop index if exists submissions_duplicate_of_idx;

pragma legacy_alter_table=on;

alter table submissions rename to submissions_zt0_pre;

create table submissions (
  submission_id text primary key,
  created_at text not null default (datetime('now')),
  uploaded_at text,
  expires_at text,
  origin text not null check (origin in ('project_anchor', 'community')),
  submitter_id text,
  ticket_id text,
  status text not null,
  status_reason text,
  bundle_schema_version text,
  raw_bundle_sha256 text not null,
  raw_bundle_r2_key text,
  raw_bundle_size_bytes integer,
  suite_release_id text,
  suite_manifest_sha256 text,
  scorecard_id text,
  model_identity_digest text,
  model_display_name text,
  lane_id text,
  tier text,
  validator_version text,
  validator_commit text,
  validated_at text,
  projection_schema_version text,
  projection_sha256 text,
  projection_r2_key text,
  public_artifact_manifest_sha256 text,
  public_artifact_r2_key text,
  redaction_status text not null default 'not_checked' check (redaction_status in ('not_checked', 'passed', 'failed', 'public_projection_only')),
  trust_label text,
  verification_level text check (verification_level is null or verification_level in ('bundle_rescored', 'spot_reproduced')),
  publish_state text not null default 'hidden' check (publish_state in ('hidden', 'preview', 'published')),
  published_at text,
  supersedes_submission_id text references submissions(submission_id),
  run_payload_sha256 text,
  duplicate_of text,
  idempotency_key text not null unique,
  submitter_display_name text,
  check (idempotency_key = raw_bundle_sha256)
);

insert into submissions (
  submission_id, created_at, uploaded_at, expires_at, origin, submitter_id, ticket_id, status,
  status_reason, bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key, raw_bundle_size_bytes,
  suite_release_id, suite_manifest_sha256, scorecard_id, model_identity_digest, model_display_name,
  lane_id, tier, validator_version, validator_commit, validated_at, projection_schema_version,
  projection_sha256, projection_r2_key, public_artifact_manifest_sha256, public_artifact_r2_key,
  redaction_status, trust_label, verification_level, publish_state, published_at,
  supersedes_submission_id, run_payload_sha256, duplicate_of, idempotency_key, submitter_display_name
)
select
  submission_id, created_at, uploaded_at, expires_at, origin, submitter_id, ticket_id, status,
  status_reason, bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key, raw_bundle_size_bytes,
  suite_release_id, suite_manifest_sha256, scorecard_id, model_identity_digest, model_display_name,
  lane_id, tier, validator_version, validator_commit, validated_at, projection_schema_version,
  projection_sha256, projection_r2_key, public_artifact_manifest_sha256, public_artifact_r2_key,
  redaction_status, trust_label, verification_level, publish_state, published_at,
  supersedes_submission_id, run_payload_sha256, duplicate_of, idempotency_key, submitter_display_name
from submissions_zt0_pre;

drop table submissions_zt0_pre;

pragma legacy_alter_table=off;

create unique index submissions_raw_bundle_sha256_uq on submissions(raw_bundle_sha256);
create unique index submissions_ticket_id_uq on submissions(ticket_id);
create index submissions_status_idx on submissions(status);
create index submissions_publish_state_idx on submissions(publish_state);
create index submissions_run_payload_sha_idx on submissions(run_payload_sha256);
create index submissions_duplicate_of_idx on submissions(duplicate_of);

-- Part 2 — ZT-0 tables.

create table if not exists submission_transitions (
  id integer primary key autoincrement,
  submission_id text not null,
  from_status text,
  to_status text not null,
  publish_state text,
  actor text not null,
  reason text,
  created_at text not null default (datetime('now'))
);

create index if not exists submission_transitions_submission_id_idx
  on submission_transitions(submission_id);

create table if not exists ops_settings (
  key text primary key,
  value text not null,
  disabled_by text,
  updated_at text not null default (datetime('now'))
);

insert or ignore into ops_settings (key, value, disabled_by, updated_at)
values ('auto_publish', 'off', null, datetime('now'));

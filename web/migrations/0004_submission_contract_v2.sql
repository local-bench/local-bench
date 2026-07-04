drop index if exists submissions_status_idx;
drop index if exists submissions_publish_state_idx;
drop index if exists submissions_raw_bundle_sha256_uq;
drop index if exists submissions_ticket_id_uq;
drop index if exists submissions_run_payload_sha_idx;
drop index if exists submissions_duplicate_of_idx;

pragma legacy_alter_table=on;

alter table submissions rename to submissions_contract_v1;

create table submissions (
  submission_id text primary key,
  created_at text not null default (datetime('now')),
  uploaded_at text,
  expires_at text,
  origin text not null check (origin in ('project_anchor', 'community')),
  submitter_id text,
  ticket_id text,
  status text not null check (status in ('ticketed', 'uploaded', 'pending_verification', 'validating', 'accepted', 'rejected', 'published', 'superseded')),
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
  check (idempotency_key = raw_bundle_sha256)
);

insert into submissions (
  submission_id, created_at, uploaded_at, origin, submitter_id, ticket_id, status, status_reason,
  bundle_schema_version, raw_bundle_sha256, raw_bundle_r2_key, raw_bundle_size_bytes, suite_release_id,
  suite_manifest_sha256, scorecard_id, model_identity_digest, model_display_name, lane_id, tier,
  validator_version, validator_commit, validated_at, projection_schema_version, projection_sha256,
  projection_r2_key, public_artifact_manifest_sha256, public_artifact_r2_key, redaction_status,
  trust_label, verification_level, publish_state, published_at, supersedes_submission_id, idempotency_key
)
select
  submission_id, created_at, uploaded_at,
  case origin when 'community_submission' then 'community' else origin end,
  submitter_id, ticket_id, status, status_reason, bundle_schema_version, raw_bundle_sha256,
  raw_bundle_r2_key, raw_bundle_size_bytes, suite_release_id, suite_manifest_sha256, scorecard_id,
  model_identity_digest, model_display_name, lane_id, tier, validator_version, validator_commit,
  validated_at, projection_schema_version, projection_sha256, projection_r2_key,
  public_artifact_manifest_sha256, public_artifact_r2_key, redaction_status, trust_label,
  verification_level, publish_state, published_at, supersedes_submission_id, idempotency_key
from submissions_contract_v1;

drop table submissions_contract_v1;

pragma legacy_alter_table=off;

create unique index submissions_raw_bundle_sha256_uq on submissions(raw_bundle_sha256);
create unique index submissions_ticket_id_uq on submissions(ticket_id);
create index submissions_status_idx on submissions(status);
create index submissions_publish_state_idx on submissions(publish_state);
create index submissions_run_payload_sha_idx on submissions(run_payload_sha256);
create index submissions_duplicate_of_idx on submissions(duplicate_of);

create table if not exists rate_counters (
  bucket_key text primary key,
  window_start text not null,
  count integer not null
);

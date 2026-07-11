create table if not exists maintainer_verification_attestations (
  submission_id text not null references submissions(submission_id),
  raw_bundle_sha256 text not null,
  projection_object_sha256 text not null,
  coding_receipt_sha256 text not null,
  suite_release_id text not null,
  suite_manifest_sha256 text not null,
  maintainer_key_id text not null,
  decision text not null check (decision in ('verified', 'not_verified')),
  attested_at text not null default (datetime('now')),
  revision integer not null,
  primary key (submission_id, revision)
);

create index if not exists maintainer_attestations_binding_idx
  on maintainer_verification_attestations(submission_id, raw_bundle_sha256, projection_object_sha256, revision desc);

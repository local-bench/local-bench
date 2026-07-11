alter table submissions add column state_revision integer not null default 0;
alter table submissions add column projection_object_sha256 text;
alter table submissions add column community_model_group_id text;
alter table submission_transitions add column state_revision integer;
create unique index if not exists submission_transitions_revision_uq
  on submission_transitions(submission_id, state_revision) where state_revision is not null;

create unique index if not exists submissions_projection_object_sha_uq
  on submissions(projection_object_sha256) where projection_object_sha256 is not null;

create table if not exists publication_control (
  singleton integer primary key check (singleton = 1),
  publication_revision integer not null,
  active_snapshot_id text,
  edge_block_revision integer not null default 0,
  updated_at text not null default (datetime('now'))
);
insert or ignore into publication_control (singleton, publication_revision) values (1, 0);

create table if not exists publication_snapshots (
  snapshot_id text primary key,
  publication_revision integer not null,
  snapshot_digest text not null,
  total_count integer not null,
  created_at text not null,
  activated_at text,
  output_tree_digest text,
  build_input_manifest_digest text
);

create table if not exists publication_snapshot_rows (
  snapshot_id text not null references publication_snapshots(snapshot_id),
  ordinal integer not null,
  submission_id text not null,
  projection_object_sha256 text not null,
  projection_r2_key text not null,
  publish_state text not null,
  state_revision integer not null,
  suite_release_id text not null,
  suite_manifest_sha256 text not null,
  decision_class text not null,
  trust_class text not null,
  community_model_group_id text not null,
  primary key (snapshot_id, ordinal),
  unique (snapshot_id, submission_id)
);

create table if not exists publication_edge_blocks (
  submission_id text primary key,
  blocked_at text not null default (datetime('now')),
  reason text not null,
  publication_revision integer not null
);

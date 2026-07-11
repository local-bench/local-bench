create table if not exists community_model_groups (
  community_model_group_id text primary key check (community_model_group_id glob 'community-group:[0-9a-f]*'),
  declared_model_name text not null,
  identity_label text not null default 'community-declared, identity-unverified',
  created_at text not null default (datetime('now'))
);

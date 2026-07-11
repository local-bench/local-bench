create table if not exists community_model_groups (
  community_model_group_id text primary key check (
    length(community_model_group_id) = 48
    and substr(community_model_group_id, 1, 16) = 'community-group:'
    and substr(community_model_group_id, 17) not glob '*[^0-9a-f]*'
  ),
  declared_model_name text not null,
  identity_label text not null default 'community-declared, identity-unverified',
  created_at text not null default (datetime('now'))
);

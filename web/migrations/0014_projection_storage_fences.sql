create table if not exists projection_storage_fences (
  projection_object_sha256 text primary key,
  owner text not null,
  created_at text not null default (datetime('now'))
);

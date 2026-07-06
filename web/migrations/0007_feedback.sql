create table if not exists feedback (
  id text primary key,
  message text not null,
  contact text,
  created_at text not null,
  ip_hash text not null,
  status text not null default 'new' check (status in ('new', 'read'))
);

create index if not exists idx_feedback_status_created
  on feedback (status, created_at desc);

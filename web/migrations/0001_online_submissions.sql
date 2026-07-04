create table if not exists suites (
  suite_id text primary key,
  version text not null,
  suite_hash text not null,
  manifest_url text not null,
  active integer not null default 1,
  created_at text not null default (datetime('now'))
);

create table if not exists submissions (
  submission_id text primary key,
  public_key text not null,
  suite_id text not null,
  suite_hash text not null,
  status text not null,
  server_nonce text not null,
  r2_key text not null,
  bundle_sha256 text,
  manifest_payload_sha256 text,
  size_bytes integer,
  issued_at text not null,
  updated_at text not null
);

create index if not exists submissions_status_idx on submissions(status);
create index if not exists submissions_bundle_sha_idx on submissions(bundle_sha256);

create table if not exists verification_jobs (
  job_id integer primary key autoincrement,
  submission_id text not null references submissions(submission_id),
  status text not null,
  result_r2_key text,
  error text,
  created_at text not null,
  updated_at text not null
);

create table if not exists admin_decisions (
  decision_id integer primary key autoincrement,
  submission_id text not null references submissions(submission_id),
  decision text not null,
  reason text not null,
  decided_at text not null
);

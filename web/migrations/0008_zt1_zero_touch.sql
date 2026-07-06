alter table submissions add column identity_class text;
alter table submissions add column board_identity_key text;
alter table submissions add column board_display_label text;
alter table submissions add column provisional_until text;
alter table submissions add column provisional_reason text;
alter table submissions add column zt1_decision text;
alter table submissions add column zt1_decision_reason text;
alter table submissions add column zt1_decided_at text;
alter table submissions add column zt1_coding_state text;
alter table submissions add column zt1_flags_json text;

create index if not exists submissions_zt1_decision_idx
  on submissions(zt1_decision, publish_state, provisional_until);

create index if not exists submissions_identity_class_idx
  on submissions(identity_class, board_identity_key);

create table if not exists submission_decision_log (
  id integer primary key autoincrement,
  submission_id text,
  actor text not null,
  event text not null,
  reason text not null,
  details_json text not null default '{}',
  created_at text not null default (datetime('now'))
);

create index if not exists submission_decision_log_created_idx
  on submission_decision_log(created_at);

create index if not exists submission_decision_log_submission_idx
  on submission_decision_log(submission_id);

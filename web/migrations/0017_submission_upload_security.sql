alter table submissions add column ticket_envelope_json text;
alter table submissions add column upload_declared_size_bytes integer
  check (upload_declared_size_bytes is null or upload_declared_size_bytes between 1 and 52428800);
alter table submissions add column upload_target_url text;

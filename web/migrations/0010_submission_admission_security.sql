-- Separate upload authority from public queue IDs and index exact GGUF identity checks.
alter table submissions add column upload_capability_sha256 text;

create index if not exists submissions_model_identity_status_idx
  on submissions(model_identity_digest, status);

-- 0005: submitter credit (owner request 2026-07-04)
-- Optional human-readable display name bound to a submission at ticket time.
-- Identity remains the Ed25519 keypair (submitter_id = public_key:<hex>); this
-- column is display-only credit, surfaced on the public row and the board, and
-- implicitly moderated by manual admin acceptance before anything publishes.
alter table submissions add column submitter_display_name text;

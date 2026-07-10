-- Preserve the public model label supplied when a ticket is issued so the
-- pending-verification queue can identify work without exposing bundle hashes or submitter keys.
alter table submissions add column declared_model_slug text;

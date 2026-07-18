create table accounts (
  account_id text primary key
    check (length(account_id) = 37 and substr(account_id, 1, 5) = 'acct_' and substr(account_id, 6) not glob '*[^0-9a-f]*'),
  github_user_id text not null unique
    check (length(github_user_id) between 1 and 32 and github_user_id not glob '*[^0-9]*'),
  github_login text not null
    check (length(github_login) between 1 and 40 and github_login not glob '*[^A-Za-z0-9-]*'),
  created_at text not null default (datetime('now')),
  revoked_at text
);

create table account_keys (
  public_key_hex text primary key
    check (length(public_key_hex) = 64 and public_key_hex not glob '*[^0-9a-f]*'),
  account_id text not null references accounts(account_id),
  bound_at text not null default (datetime('now')),
  binding_signature text not null
    check (length(binding_signature) = 128 and binding_signature not glob '*[^0-9a-f]*')
);

create index account_keys_account_id_idx on account_keys(account_id);

create table github_oauth_device_codes (
  device_code_handle text primary key
    check (length(device_code_handle) = 36 and substr(device_code_handle, 1, 4) = 'dch_' and substr(device_code_handle, 5) not glob '*[^0-9a-f]*'),
  device_code text not null check (length(device_code) between 1 and 200),
  created_at text not null default (datetime('now')),
  expires_at text not null,
  interval_seconds integer not null check (interval_seconds between 1 and 60),
  last_polled_at text
);

create index github_oauth_device_codes_expiry_idx on github_oauth_device_codes(expires_at);

create table github_oauth_states (
  state_handle text primary key
    check (length(state_handle) = 38 and substr(state_handle, 1, 6) = 'state_' and substr(state_handle, 7) not glob '*[^0-9a-f]*'),
  created_at text not null default (datetime('now')),
  expires_at text not null
);

create index github_oauth_states_expiry_idx on github_oauth_states(expires_at);

alter table submissions add column account_id text references accounts(account_id);
alter table submissions add column github_login text;

# Submission slice — BATCH 2 spec (2026-06-30)

Implements oracle build-order steps 5,7,8,9 on top of the committed FOUNDATION (commit 440f540;
`docs/foundations/submission-slice-design-decided-2026-06-30.md`). The oracle red-team already
blessed this design (incl. the D1 schema below) — this is implementation, not new architecture.

Split for tractable QA on live-site infra:
- **Batch 2a (THIS task)** — data/verification spine, fully offline-testable, no secrets, no TS edge.
- **Batch 2b (next task)** — Cloudflare Workers intake + board partial-row UI + web-scaffolding reconcile.

Hard rules unchanged: branch `codex/local-bench-online-backend`; `cli/runs/board/board_v1.json`
BYTE-IDENTICAL (do not touch); do NOT set any secret; do NOT push; do NOT deploy; the site stays
private-gated. Everything must build + unit-test locally WITHOUT R2 creds or the 3 secrets.

## Batch 2a scope (build now)

### 1. Site-served 4-axis suite release
- Produce an immutable, hash-pinned suite release for coverage profile `partial-text-code-4axis-v1`
  = {mmlu_pro, ifbench, tc_json_v1, lcb}, served under `web/public/suites/<suite_release_id>/` with a
  `suite_release_manifest_v1` (canonical `suite_manifest_sha256` via the foundation's `suite_release.py`).
- KEEP existing `core-text-v1` as the honest 3-axis endpoint subset (`core-text-3axis-v1`); do not
  conflate. Both coverage profiles must be representable.
- The runner must be able to PULL this 4-axis suite release from the site path and verify its hash
  before running (extend the existing `suite_resolver.py` remote-manifest path; the manifest URL is a
  local/relative path or the private site for now — no live fetch in tests, use a local fixture).
- Redaction/license: confirm `lcb.jsonl` license permits public serving; if uncertain, FLAG it in the
  manifest + a NOTICE rather than silently publishing. Do not expose local paths.

### 2. D1 schema + migration (index only, NOT scoring truth)
Add a versioned D1 migration (e.g. `web/migrations/000X_submissions.sql`) creating two tables, per the
oracle design. D1 stores pointers/index/queue-state only; the immutable bundle (R2) + the
accepted projection are the truth.

`submissions` columns: `submission_id` (ULID/UUID PK), `created_at`, `uploaded_at`, `origin`
(`project_anchor`|`community_submission`), `submitter_id`, `ticket_id` (nullable), `status`
(`ticketed`|`uploaded`|`validating`|`accepted`|`rejected`|`published`|`superseded`), `status_reason`,
`bundle_schema_version`, `raw_bundle_sha256`, `raw_bundle_r2_key`, `raw_bundle_size_bytes`,
`suite_release_id`, `suite_manifest_sha256`, `scorecard_id`, `model_identity_digest`,
`model_display_name`, `lane_id`, `tier`, `validator_version`, `validator_commit`, `validated_at`,
`projection_schema_version`, `projection_sha256`, `projection_r2_key`,
`public_artifact_manifest_sha256`, `public_artifact_r2_key`, `redaction_status`
(`not_checked`|`passed`|`failed`|`public_projection_only`), `trust_label`, `verification_level`
(`bundle_rescored`|`spot_reproduced`|… never `verified` in v0), `publish_state`
(`hidden`|`preview`|`published`), `published_at`, `supersedes_submission_id`, `idempotency_key`
(= `raw_bundle_sha256`; UNIQUE).

`board_entries` columns: `entry_id` (PK), `submission_id` (FK), `board_schema_version`,
`published_at`, `visibility` (`private`|`preview`|`public`), `origin`, `trust_label`,
`verification_level`, `model_display_name`, `model_family`, `model_file_sha256`, `model_quant_label`,
`runtime_name`, `runtime_version`, `hardware_summary`, `lane_id`, `tier`, `suite_release_id`,
`suite_manifest_sha256`, `scorecard_id`, `coverage_profile_id`, `headline_complete`,
`headline_score` (nullable; NULL for partial), `partial_composite` (nullable),
`measured_headline_weight`, `missing_headline_weight`, `known_headline_contribution`, `rank_scope`,
`global_rank` (NULL unless full headline), `scope_rank` (nullable), `axis_scores_json`,
`bench_scores_json`, `conformance_json`, `n_scored`, `n_errors`, `warning_count`, `projection_sha256`,
`bundle_sha256`, `public_artifact_manifest_sha256`.
Defer `verification_events` to a later batch. Provide a tiny TS/JS (or Python) helper that maps an
`accepted_result_projection_v1` → a `board_entries` row, with a unit test.

### 3. `localbench verify-submission` glue (Python = authoritative verifier)
- New CLI command that performs the authoritative v0 verification offline: given a bundle (local path
  now; an R2-key adapter is added in 2b), it runs `validate-submission-bundle` + `rescore-bundle`
  (foundation), writes the `accepted_result_projection_v1`, and emits a status-update payload
  (`accepted`/`rejected` + reason + projection_sha256 + projection path) that 2b's Worker will apply
  to D1. It must NOT depend on D1 or the network. Record validator_version/commit/validated_at.
- This is the "owner-run command / GH Action" verifier the oracle specified — NOT an always-on service.
- Golden test: running it on the pilot bundle yields `accepted=false` (because validate →
  publishable:false) with the exact blocking_reasons; on a synthetic publishable fixture it yields a
  byte-identical projection.

## OUT of scope for 2a (→ 2b or later)
Cloudflare Worker routes / R2 upload wiring / ticket issuance / the board UI rendering; reconciling the
existing `web/functions` submission scaffolding TS; setting secrets; deploy/push; GPU rerun; community
accounts; trust-tier machinery; always-on verifier; public raw-transcript release.

## Definition of done (2a)
- Branch `codex/local-bench-online-backend`. `board_v1.json` byte-identical. No secrets, no push, no deploy.
- Unit tests: suite release (4-axis manifest + canonical hash + runner pull-from-local-fixture +
  hash-verify), D1 migration applies on a local/in-memory SQLite or `wrangler d1` local + projection→
  board_entries mapper, and `verify-submission` golden tests (pilot → rejected w/ blockers; publishable
  fixture → byte-identical projection). Full `pytest cli\tests` green; any new JS/TS tests green.
- Concise change summary: files touched, the suite_release_id + its suite_manifest_sha256, the D1
  migration name, and exactly what still needs secrets/R2 creds to function live (for 2b + go-live).

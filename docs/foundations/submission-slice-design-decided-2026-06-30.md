# Submission slice — DECIDED design (2026-06-30)

Authoritative implementation spec for the first submission-slice **foundation** batch. Resolves the
open questions in `docs/deploy/submission-slice-design-brief-2026-06-30.md` using the GPT-5.5 Pro
oracle red-team (2026-06-30) + Claude synthesis. Coverage problem: `docs/deploy/suite-alignment-finding-2026-06-29.md`.
Golden fixture: `runs/campaigns/wave0-gemma-12b-q4xl-cal-20260629/localbench-run.json`.
Single source of truth for axis weights/membership: `cli/src/localbench/scoring/axes.py`.

> Supersedes `docs/foundations/result-bundle-v1-contract-DRAFT-2026-06-30.md` (which proposed
> adopt-as-is). The decision is: **split into three contracts + change the schema before freezing.**

## Decisions (resolved)

1. **Three separate contracts**, not one bundle:
   - `result_bundle_v1` — pure measurement/audit record the runner emits. Hashable/validatable
     offline with no site or D1 contact.
   - `submission_envelope_v1` — submission/auth/upload layer (ticket). Lives OUTSIDE the bundle.
   - `accepted_result_projection_v1` — verifier-DERIVED public board fields. Submitter never authors it.
2. **Python is the authoritative validator/rescorer**, not Cloudflare Workers. (CF wiring is a LATER
   batch — out of scope here.) Build the offline Python core now.
3. **Publish only labelled PARTIAL rows until agentic runs** — `headline_score: null`, scoped scores,
   no global rank for partial coverage.
4. **The site must serve the exact suite a row used** — keep `core-text-v1` as an honest 3-axis subset,
   add a 4-axis coverage profile for the pilot's bench set; canonical suite hash = hash of a
   deterministic **suite release manifest**. Fix the `axes.py` vs `suite/v1` agentic-membership divergence.
5. **Sequencing:** the existing pilot bundle is **submission #0 / validator fixture** — it must validate
   as `publishable:false` with exact blocking reasons (top_k/seed null, model/runtime identity missing,
   suite not site-released). The first PUBLISHED row needs a sampler-pinned rerun (a later GPU step,
   NOT in this batch).

## In scope for THIS batch (all non-GPU, no secrets, no CF/D1 wiring, no push)

### A. Three contract schemas + validators
Define each as a versioned JSON schema + Python dataclass/validator under the existing
`localbench` package (mirror the style of current `_types`/scoring modules). Add a top-level
`schema_version` string to each.

**`result_bundle_v1`** — start from the current `localbench.run.v1` emitter and CHANGE:
- Collapse the dual `schema: localbench-run-v0` + `schema_version: localbench.run.v1` into a single
  `schema_version: "localbench.result_bundle.v1"`. Optional non-semantic `producer: "localbench-cli"`.
- REMOVE submission/auth fields from the bundle (they move to the envelope): `submission_ticket_id`,
  `server_nonce`, `issued_at`, `account`.
- REMOVE submitter-authored trust fields `trust_tier` / `serving_verification_level`. The runner MAY
  self-report `serving_mode: "external_openai_compatible_endpoint"`. `origin` / `trust_label` /
  `verification_level` are assigned later by the verifier/projection, never by the runner.
- REPLACE the bare top-level `composite` with a `scores` object:
  `{headline_score, partial_composite, partial_composite_scope, measured_headline_weight,
  missing_headline_weight, known_headline_contribution, rank_scope}`. For the pilot:
  `headline_score=null, partial_composite=0.7473, partial_composite_scope="measured_headline_axes",
  measured_headline_weight=0.50, missing_headline_weight=0.50, known_headline_contribution=0.3737,
  rank_scope="partial-text-code-4axis-v1"`. Keep `headline_complete` (bool). Keep `axis_status`.
- RENAME `manifest.integrity.canonical` → `integrity.publishable` (bool) and add
  `integrity.validation_profile`, `integrity.blocking_reasons[]`, `integrity.missing_required_fields[]`.
- ADD canonical suite identity under `manifest.suite`: `suite_release_id`, `suite_manifest_sha256`,
  `suite_hash_algorithm`, `coverage_profile_id`, `axis_membership`, `bench_membership` (keep existing
  `item_set_hashes`), `license_manifest_sha256`.
- ADD `manifest.provenance`: `localbench_repo_commit`, `dirty_tree`, `cli_version`, `python_version`,
  `dependency_lock_hash`, `scorer_package_version`, `extractor_versions`, `runner_build_id` (nullable).
- Sampler determinism (publishable-required): `manifest.sampling` must carry `temperature, top_k,
  top_p, min_p, seed, determinism_policy` (+ optional `engine_sampler_notes`).
- Model/runtime identity (publishable-required): the fields the pilot self-listed as missing
  (model.family/quant_label/file_name/file_size_bytes/file_sha256/format/tokenizer_digest/
  chat_template_digest; runtime.name/version/kv_cache_quant/ctx_len_configured/parallel_slots/
  build_flags; GPU driver/CUDA/backend version).
- REMOVE/sanitize `output_path` (relative to artifact package, or keep only in the private raw bundle
  with redaction status — never a public absolute Windows path).
- KEEP `items[]` (full per-item incl reasoning_text), `totals`, `conformance`, `warnings`,
  `rendered_prompt_sample`.

**`submission_envelope_v1`** — ticket/upload layer: `ticket_id`, `submitter_id`,
`origin` (`project_anchor`|`community_submission`), `allowed_schema` (e.g.
`localbench.result_bundle.v1`), `expected_suite_release_id`/`expected_suite_manifest_sha256`
(nullable), `accepted_suite_terms`, `max_upload_bytes`, `expiry`, `one_use` (bool),
`declared_model_slug` (optional, NOT authoritative), `bundle_sha256` (idempotency key). The ticket
binds submission facts only; it does NOT attest the model ran.

**`accepted_result_projection_v1`** — verifier-derived, board-safe ONLY: model display identity +
file hash/quant/runtime, `suite_release_id`/`suite_manifest_sha256`, `scorecard_id`,
`coverage_profile_id`, `headline_complete`, the scoped `scores`, per-axis `{score,n,ci,status}`,
conformance summary, artifact hashes (bundle_sha256, projection_sha256, public_artifact_manifest_sha256),
`origin`, `trust_label`, `verification_level`, validator provenance (validator_version/commit,
validated_at). No raw transcripts, no local paths, no secrets.

### B. Suite release manifest v1 + fix membership divergence
- Define a deterministic `suite_release_manifest_v1`: `suite_release_id`, `suite_semver`/immutable
  tag, `suite_hash_algorithm`, full file list with SHA-256, `item_set_hashes`, `axis_membership`,
  `bench_membership`, `scorecard_id`, `registry_digest`, scorer/extractor versions,
  `license_manifest_sha256`, `coverage_profile_id`. **Canonical `suite_manifest_sha256` = hash of this
  manifest's canonical serialization** (document the algorithm + canonical form; exclude any timestamp
  from the hashed content).
- Define coverage profiles: `core-text-3axis-v1` (mmlu_pro+ifbench+tc_json_v1; weight 0.40; NOT
  headline) and `partial-text-code-4axis-v1` (mmlu_pro+ifbench+tc_json_v1+lcb; weight 0.50; partial).
- **FIX the membership divergence:** `axes.py` (SoT) maps agentic=`appworld_c`; `suite/v1/suite.json`
  maps agentic=`[bfcl, bfcl_multi_turn]`. Make suite manifests GENERATED-FROM or CHECKED-AGAINST
  `axes.py`; add/repair the test that asserts suite membership matches the registry. Do NOT silently
  edit `suite/v1/suite.json` item content — reconcile the axis membership only, and document it.

### C. Offline Python validator + rescorer + projection generator
- `validate-submission-bundle <bundle>`: schema check, recompute bundle/suite hashes, verify item IDs,
  scorecard, conformance; emit `publishable: bool` + exact `blocking_reasons`. Runs offline (no D1/site).
- `rescore-bundle <bundle>`: deterministic rescore from item-level responses via the SAME Python scorer
  path the CLI uses; emit `accepted_result_projection_v1`.
- **Pilot fixture (golden):** the existing pilot bundle MUST validate as `publishable:false` with
  blocking_reasons covering {sampler top_k/seed unpinned, model identity hashes missing, runtime
  identity missing, suite not site-released}. Rescore MUST reproduce the per-axis numbers
  (mmlu_pro 0.7725, ifbench 0.6871, tc_json_v1 0.7364, lcb 0.8527) and `partial_composite=0.7473`,
  and be **byte-identical on a second rescore**.

### D. Runner metadata + sampler-pin patch
- Populate the publishable-required fields above: model file hashing (GGUF sha256 + size + name +
  quant/format/family), tokenizer + chat-template digests, runtime identity (from llama-server `/props`
  or launch flags), repo/scorer/CLI/python provenance, suite_release_id/hash, redaction-safe paths.
- Add sampler-pin support: a publishable lane that sets `top_k=1` + explicit `seed` +
  `determinism_policy`; do NOT rely on `temperature=0` alone. (Do NOT launch any GPU run — just the
  config/code/flag plumbing + unit tests.)
- Runner sets `integrity.publishable` + `blocking_reasons` + `missing_required_fields` accordingly.

## OUT of scope this batch (do NOT build)
Cloudflare Workers intake / R2 upload wiring / D1 tables / Queue consumer; the GPU rerun; setting any
secret; community accounts; trust-tier machinery beyond conservative enum labels; automatic spot
reproduction; the agentic/AppWorld runner; public raw-transcript release; always-on verifier service;
full leaderboard ranking. Note (do not break) the existing `web/functions` submission scaffolding —
reconciling it with these contracts is the NEXT batch.

## Definition of done
- Branch `codex/local-bench-online-backend`. **`cli/runs/board/board_v1.json` byte-identical** (do not
  touch). **Do not set secrets. Do not push to any remote.**
- New/updated unit tests: the three contracts (round-trip + validation), suite release manifest +
  membership-vs-axes.py assertion, validator (`publishable:false` + exact blocking_reasons on the pilot
  fixture), rescorer (reproduces pilot numbers + byte-identical projection on re-run), runner field
  population. Full `pytest cli/tests` green; report pass/skip counts.
- Provide a concise change summary (files touched, new modules, schema versions, test results) and an
  explicit list of any field renames that affect the existing `localbench.run.v1` emitter, so the web
  side can be reconciled next batch.

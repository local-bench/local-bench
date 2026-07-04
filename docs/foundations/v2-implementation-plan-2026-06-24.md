# V2 (community submission + verification) — implementation plan (oracle-synthesized, 2026-06-24)

GPT-5.5 Pro (oracle) consult `v2-submission-implementation-plan`, built on the 2026-06-23 design
(`submission-verification-design.md`) + the 2026-06-24 launch plan. This is the IMPLEMENTATION plan
(the design is settled). **Verdict: invert the design's nominal build order** — build the
deterministic submission contract + bundle builder + verifier + server-side recompute + dedup +
trust-label core FIRST (fully offline, adversarially tested), and leave live Cloudflare ingest, OAuth,
R2, D1, GPU reruns, and the sentinel until the logical core passes offline. Execution: Codex builds,
Claude reviews/tests.

## Milestones

- **M0 — freeze the submission contract (not the cloud path):** submission-format version
  `localbench.submission-bundle.v1`; JSON schemas for manifest / item-transcript / verification-result;
  canonicalization spec (sorted-key UTF-8 JSON, no NaN, deterministic JSONL + archive ordering); golden
  fixtures; an `offline` ticket mode (no OAuth/R2/D1 needed). Forces the key security decision early:
  **the verifier ignores client aggregates and re-scores from raw per-item outputs.**
- **M1 — offline bundle builder + offline verifier + frozen re-score (FIRST Codex task; full spec below).**
- **M2 — local submission SERVICE core with FAKE adapters:** wrap `verify_bundle_offline()` in the
  `SubmissionService` the Worker will later call, backed by `InMemoryObjectStore/StatusStore`,
  `FakeIdentityProvider/NonceStore/Queue`, `FixedClock/SecretProvider`. Proves Cloudflare is just adapters.
- **M3 — deterministic spot-rerun SAMPLER + review-job planner (offline):** `sample_seed =
  HMAC(server_secret, bundle_sha256 || submission_id)`; policy buckets (low-rank / new-family / top-25 /
  top-10-or-record / anchor); hidden-after-upload selection. Build selection logic now; defer GPU execution.
- **M4 — Cloudflare adapter SKELETON (local-only):** `workers/submissions/` entry + adapters +
  `wrangler.toml.example` + D1 migrations, tested against Miniflare/local; NO production wiring. (Python
  Workers run on Pyodide → a scorer-dependency audit is a real gate; keep core pure/stdlib where possible.)
- **M5 — live ticket/upload/status path (FIRST creds needed):** `POST /ticket`, R2 presigned `PUT`,
  `POST /complete`, `GET /:id/status`. Worker must NOT proxy bundles (100 MB body cap) — issue R2
  presigned PUT, client uploads direct.
- **M6 — GitHub OAuth + Turnstile + quotas + account-bound keys** (identity last; the offline verifier
  already validates `account_id`/`server_nonce`/public-key binding through an interface).
- **M7 — GPU rerun executor + private sentinel + human gate** (NOT part of the offline core; strict
  verifier-stack matching gates "spot-reproduced"; everything else stays "community re-scored").

## Build-now (no creds) vs defer

**Build + fully unit-test NOW:** schemas; canonical JSON/hash/archive; `submit pack --offline`;
`submit verify-offline`; Ed25519 manifest sign + verify; bundle unpack + path allowlist (zip-slip);
size/record limits; suite-hash validation (reuse `suite_verify.verify_suite_dir()`/`suite_hash()`);
scorecard validation (reuse `scorecard_identity()` → `scorecard-v1.3`); **server-side re-score reusing
the frozen scorer (ignore client aggregates)**; board-compatible recomputed run object; duplicate
detection (bundle/manifest/per-item hashes + run nonce); trust-label state machine (only
`community_re_scored`, never "verified"); HMAC spot-rerun sampler logic; in-memory store/identity/
queue/nonce fakes; advisory-agent input sanitizer.

**Defer / stub (creds or GPU):** deployed ingest Worker; R2 presigned upload; D1 status rows; GitHub
OAuth; email magic-link; Turnstile; account-bound key registration (stub via fake identity); live
quotas/reputation; GPU spot-rerun executor; private sentinel bank+execution; human-review UI; Pages
publishing; advisory LLM reviewer.

## Architecture — ports & adapters (the Worker is a transport wrapper over a pure deterministic core)

Ports (Protocols): `ObjectStore`, `StatusStore`, `IdentityProvider`, `NonceStore`, `WorkQueue`,
`SecretProvider`, `Clock`, `SignatureProvider`. Core pipeline:

```
read bundle bytes -> enforce archive/path/size limits -> parse manifest -> verify canonical manifest
hash -> verify Ed25519 signature over manifest PAYLOAD (not zip bytes) -> validate JSON schemas ->
validate suite_hash + scorecard_id -> validate item IDs (exact allowed set; no unknown/missing/dup) ->
verify per-item hashes -> recompute item scores from RAW outputs via frozen scorer -> recompute bench
aggregates + chance-corrected Index + CIs -> compare self-reported fields for AUDIT ONLY -> dedup keys
-> conservative trust state -> plan rerun/review jobs -> persist verification result
```

**Hard rule for the build agent:** NO Cloudflare import, NO network call, NO credential read inside
`localbench/submissions/{bundle,validate,rescore,verify,trust,dedup}.py`. Only adapters know Cloudflare exists.

## Shared CLI<->verifier contract (one source, imported by both)

Deterministic zip (fixed file order/timestamps/modes/compression). Layout: `manifest.json`,
`items.jsonl`, `run.original.json` (optional audit, never authoritative), `environment.json` (optional,
allowlisted). **Signature is over the manifest `payload`, not the final zip** (avoids circularity);
`bundle_sha256` computed outside the signature. Manifest payload carries: submission_format, created_at,
run_nonce, ticket{mode,submission_id,server_nonce,account_id}, cli{name,version}, suite{id,hash,
item_set_hashes}, scorecard{version,id,registry_digest}, lane{name,sampler}, model_claim{display_name,
artifact_url,gguf_sha256,tokenizer_sha256,chat_template_sha256,quantization}, files[{path,sha256,size}],
counts{items_total,by_bench}. Item JSONL record: schema_version, sequence_index, bench, item_id,
suite_item_sha256, request{...}, response{text,finish_reason,error}, usage, timing, client_scoring
(audit only — IGNORED for scoring). Verifier REQUIRED for a public v1 score: suite_hash exact;
scorecard_id exact; item set exact (no unknown/dup/missing); each item has response.text or explicit
error; client_scoring + submitted aggregates + submitted Index all IGNORED; official score RECOMPUTED.

## Top implementation risks -> tests (full matrix in oracle session)

Trusting client scores -> tampered fixture (wrong raw output claims correct:true) must recompute false.
Scorecard/suite drift -> pin `scorecard_id`; one-byte-changed suite file must reject. Signature
canonicalization -> golden payload bytes + fixed key/sig; mutate one byte -> fail. Circular bundle hash
-> sign payload+file-hashes, compute bundle_sha outside. Zip-slip/zip-bomb -> malicious-path + oversize
fixtures. Dup/missing/unknown items -> fixtures each. Determinism -> verify same bundle 3x = byte-
identical verification.json (fixed bootstrap seed). Reimplementing the scorer -> rescore MUST call the
existing scorer/extractor + `scorecard_identity()`; reject duplicated scoring math in review.

---

## M1 — Codex build-agent task spec (self-contained, offline, no creds)

**Title:** Offline submission bundle + verifier core for localbench v2, no cloud dependencies.

**Goal:** a reviewable change letting a maintainer run, with NO network/Cloudflare/GitHub/R2/D1/email:
```
localbench submit pack --run <run.json> --suite-dir suite/v1 --model-name "fixture-model" \
  --signing-key <ed25519.pem> --out <out.lbsub.zip> --offline
localbench submit verify-offline <out.lbsub.zip> --suite-dir suite/v1 --out <verification.json>
```

**New package `localbench/submissions/`:** `canon.py` (canonical JSON, hashes, deterministic archive),
`contracts.py` (schema loaders + version constants), `crypto.py` (Ed25519 behind a `SignatureProvider`),
`bundle.py` (pack/unpack/manifest/files map), `validate.py` (deterministic schema + semantic),
`rescore.py` (server-side recompute from raw per-item outputs), `verify.py` (end-to-end offline
pipeline), `trust.py` (conservative trust-label state machine), `dedup.py` (hash keys), `ports.py`
(the Protocols above). **`schemas/`:** `submission_manifest_v1.schema.json`,
`submission_item_v1.schema.json`, `submission_verification_v1.schema.json`. **`tests/submissions/`:**
`test_bundle_pack.py`, `test_manifest_signature.py`, `test_verify_offline.py`,
`test_rescore_ignores_client_scores.py`, `test_bad_bundles.py`, `test_determinism.py`.
**Modify `cli.py`:** add `submit pack` + `submit verify-offline` ONLY; do NOT change run/suite/doctor/
compare/code/board semantics.

**Required behavior:** `submit pack` reads an existing localbench run JSON -> deterministic `.lbsub.zip`
with the manifest fields above + Ed25519 signature over the canonical payload. `submit verify-offline`
MUST: reject malformed zip paths / enforce allowlist / enforce size limits / validate manifest schema /
verify file hashes / verify Ed25519 signature / run `verify_suite_dir()` + compare `suite_hash` /
compare scorecard identity to `scorecard_identity()` / reject unknown+duplicate+missing v1 item IDs /
IGNORE client aggregate scores / IGNORE client item `correct` / recompute item scoring from RAW outputs
using the FROZEN scorer / emit `trust_label="community_re_scored"` only after recompute / emit
`publishable=false` for offline with reason `offline_ticket_not_account_bound`. If the scorer lacks a
"score raw output for suite item" entry point, add a THIN public wrapper
`localbench.scoring.public_rescore.score_public_item(bench, suite_item, response_text)` — do NOT
duplicate scorer logic in `submissions/rescore.py`.

**Fixtures (>= these):** valid; tampered_aggregate; tampered_item_correct; tampered_output;
bad_signature; wrong_scorecard; wrong_suite_hash; duplicate_item; missing_item; unknown_item;
path_traversal; oversized_manifest.

**Tests (min passing):** pack deterministic w/ fixed clock+nonce+key; manifest payload sha stable;
signature verifies for valid; signature fails after 1-byte payload mutation; file-hash mismatch rejects;
path traversal rejects; wrong suite hash rejects; wrong scorecard rejects; duplicate/missing/unknown
item rejects; client aggregate tampering does NOT change recomputed score; client item-correct tampering
does NOT change recomputed score; same valid bundle verified twice = byte-identical verification JSON;
offline verified bundle -> community_re_scored + publishable=false.

**Non-goals (do NOT implement):** Cloudflare Worker routes; R2 presigned PUT; D1; GitHub OAuth;
Turnstile; email; production quotas; Pages publication; GPU reruns; private sentinel; human-review UI;
LLM reviewer.

**Review checklist (Claude):** no client aggregate trusted; no client item-correct trusted; scorer reused
not forked; suite-hash + scorecard identity enforced; bundle canonicalization deterministic; no circular
hash mistake in the signature; bad fixtures fail for the INTENDED reason; no network/cloud/credential
code in the core; all transcript/model-name strings remain DATA, never instructions.

**Principle:** make "community re-scored" fully real OFFLINE first; make "spot-reproduced" impossible to
claim until the Cloudflare ticketing path + GPU rerun executor + sentinel + human gate exist.

*Full oracle transcript: session `v2-submission-implementation-plan` (2026-06-24), 7 milestones +
build-now/defer tables + ports + schema + risk matrix.*

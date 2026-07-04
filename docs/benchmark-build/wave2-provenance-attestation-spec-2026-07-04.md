# Wave 2 — origin threading, verdict attestations, static composite (cli/ only)

Date: 2026-07-04. Author: Claude (manager). Implementer: Codex (gpt-5.5 xhigh).
Prereqs of record: `docs/benchmark-build/submission-contract-v2-spec-2026-07-04.md`
(read §5's SUPERSEDED banner — it defines this wave's trust posture) and
`docs/benchmark-build/verdict-integrity-direct-finalize-spec-2026-07-03.md`.

## 0. Context and posture (read first)

Owner decision 2026-07-04: community submitters ship ALL five axes, agentic included.
Nothing is excluded or rejected for being dynamic. Trust is expressed by LABELS, not
gates: every carried agentic verdict gets a provenance label, the 4 static axes of any
bundle are always independently re-scored, and nothing publishes without manual admin
acceptance. The server side already landed (deployed): submission rows expose a
server-derived `origin` field (`"project_anchor" | "community"`), and community bundles
with `appworld_c` items are accepted into `pending_verification`.

This wave makes the Python side origin-aware and gives OUR OWN verdicts a cryptographic
attestation trail so anchor rows can honestly wear a stronger label than self-reported
community rows.

Scope: `cli/` and `docs/` ONLY.

### Hard constraints (violating any of these fails the wave)
- Do NOT touch `web/` (already deployed tonight; separate review track).
- Do NOT write to `cli/runs/**`. `git hash-object cli/runs/board/board_v1.json` must
  equal `3d058e6074bd781cc488c03255904b5f9599e37e` when you finish.
- Do NOT modify anything under `cli/src/localbench/data/suites/**` — released suite
  dirs are hash-frozen (their SCORECARD.json is part of the pinned suite hash).
- Do NOT change `cli/pyproject.toml` version or the `Axis` dataclass weights /
  `AXES` registry / `scorecard.SCORECARD_VERSION` / `registry_digest()` inputs —
  the ranked row was produced under scorecard-v2.1 and must not be reinterpreted.
- No secrets in code, tests, logs, or fixtures. Tests generate ephemeral keys only.
- No network access in tests.
- All existing tests must stay green: run `uv run pytest` from `cli/`.

### File map (recon 2026-07-04 — trust these, don't re-explore broadly)
- Projection/verdict-carry: `cli/src/localbench/submissions/projection.py`
  (`rescore_bundle` L27, `_dynamic_benches` L55, `_projection` L93 — hardcodes
  `origin="project_anchor"`, `trust_label="community_re_scored"`,
  `verification_level="bundle_rescored"` at L122-124, `_scored_items` L136,
  `_verdict_carried_item` L184).
- Verify orchestration: `cli/src/localbench/submissions/status_update.py`
  (`verify_submission` L13 — bundle-only args today).
- Envelope/contracts: `cli/src/localbench/submissions/foundation.py`
  (`validate_submission_envelope` L162 — allows {"project_anchor","community_submission"}).
- Server client: `cli/src/localbench/submissions/client.py` (`SubmissionEnvelope`
  TypedDict L17 with `origin` L26; `_envelope` L236; admin endpoints L157/L174).
- CLI wiring: `cli/src/localbench/cli.py` (`_submit_admin_verify` L1382,
  `_submit_admin_decision` L1409, `_submit_verify_offline` L1427, `_board` L1576).
- Crypto: `cli/src/localbench/submissions/crypto.py` (`sign_manifest_payload` L27,
  `verify_manifest_signature` L37, `load_private_key` L59);
  keys: `cli/src/localbench/submissions/keys.py` (`write_private_key` L12);
  canonical JSON: `cli/src/localbench/submissions/canon.py`.
- Bundle/zip: `cli/src/localbench/submissions/bundle.py` (`pack_submission_bundle` L25),
  `cli/src/localbench/submissions/archive.py` (`ALLOWED_MEMBERS` L13, `unpack_bundle` L27).
- Offline verify: `cli/src/localbench/submissions/verify.py` (`verify_bundle_offline` L25),
  `cli/src/localbench/submissions/rescore.py`, `cli/src/localbench/submissions/trust.py`.
- Composite: `cli/src/localbench/_scoring.py` (`composite` L169, global weights),
  `cli/src/localbench/scoring/axes.py` (AXES L50, `_validate` L168),
  `cli/src/localbench/scoring/metadata.py`, `cli/src/localbench/scoring/foundation_scores.py`
  → NOTE: score summary builder is `cli/src/localbench/submissions/foundation_scores.py`
  (`score_summary` L16, `axis_projection` L37).
- Board: `cli/src/localbench/scoring/board.py` (`build_board` L41, `write_board` L79 →
  writes board_v2.json by default), `cli/src/localbench/scoring/board_scoring.py`
  (`model_rows` L60, parameterized `_composite` L354), `board_support.py`
  (`INDEX_VERSION_FALLBACK` L23).
- Agentic direct-finalize seam: `cli/src/localbench/scoring/agentic_exec/protocol_c_loop.py`
  (`run_task` L170, verdict accepted at L360, `_finalization_record` L404),
  `cli/src/localbench/scoring/agentic_exec/sandbox.py` (`finalize` L406,
  `finalization_provenance` L429), `env_host.py` (`_handle_finalize` L158),
  `funnel.py` (`_persist_report` L349), `campaign_checkpoints.py`.
- Tests: `cli/tests/submissions/*` (fixtures in `fixtures.py`), pytest config in
  `cli/pyproject.toml`.

## W2.1 Origin threading (server row → projection)

1. `client.py`: normalize legacy `origin` value `"community_submission"` → `"community"`
   in `_envelope`; accept exactly {"project_anchor", "community"} after normalization.
   Update `foundation.validate_submission_envelope` to the same normalized set while
   still accepting the legacy string on input (normalize, don't reject — old envelopes
   exist in run artifacts).
2. Thread a REQUIRED `origin` parameter through the online admin path:
   `_submit_admin_verify` reads `origin` from the server submission row it already
   fetches (the public submission JSON now includes `origin`; if absent from a stale
   server response, fail with a typed `SubmissionValidationError` — no default) →
   `verify_submission(..., origin=...)` → `rescore_bundle(..., origin=...)` →
   `_projection` emits that origin instead of the hardcoded `"project_anchor"`.
3. The OFFLINE path (`verify_bundle_offline`, `submit verify`) has no server row:
   it keeps its current labels and does NOT invent an origin (it may pass
   `origin=None` internally; the offline report already carries
   `offline_ticket_not_account_bound`).
4. `trust_label` / `verification_level` in `_projection` become origin-aware but
   BACKWARD COMPATIBLE: keep emitting the existing strings for project_anchor rows
   (`"community_re_scored"` was a misnomer; replace as follows) —
   - project_anchor → `trust_label="project_anchor"`,
   - community → `trust_label="community_self_submitted"`,
   - `verification_level` stays `"bundle_rescored"` for both (the static axes ARE
     rescored either way).
   Update `validate_accepted_result_projection` so BOTH new labels AND the legacy
   `"community_re_scored"` validate (grandfathered artifacts on disk must not become
   invalid). Do not rewrite anything in `cli/runs/`.

## W2.2 Agentic provenance label on carried verdicts

`_projection` gains a REQUIRED field `agentic_provenance` with exactly one of:
- `"none"` — bundle contains no dynamic-bench items;
- `"project_attested"` — every carried dynamic item is covered by a VALID attestation
  (see W2.3 verification rules), or the bundle is grandfathered (below);
- `"self_reported"` — anything else (community rows; anchor rows missing/failing
  attestations). This is a LABEL, never a rejection: scoring/carry behavior is
  IDENTICAL for all three values.

Grandfather allowlist (module-level constant in projection.py, with a comment naming
the row): raw-bundle sha256
`f815ebbb78516cbdd27b379a87c9fc34fd172692ee4e4e2ce047c5c02c846f85`
(= ticket_790a73b6…, the validator-v1 ranked Gemma row, produced by the oracle-designed
direct-finalize path before attestations existed). `rescore_bundle` needs the bundle
file bytes' sha256 for this comparison — compute via `canon.sha256_file` on the input
path. Grandfathered ⇒ `"project_attested"`.

`validate_accepted_result_projection` schema: add `agentic_provenance` (required,
enum of the three values) and optional `provenance_notes: list[str]` (populated with
short reason strings whenever the label degrades to self_reported, e.g.
`"attestation_missing:appworld_c/task_42"`, `"attestation_pubkey_mismatch"`).

## W2.3 Verdict attestations (sign our own agentic verdicts)

New module `cli/src/localbench/submissions/attestation.py`:

- Record shape mirrors the bundle manifest pattern (reuse crypto.py + canon.py):
  ```json
  {
    "payload": {
      "schema": "localbench.verdict_attestation.v1",
      "bench": "appworld_c",
      "task_id": "<task id>",
      "run_id": "<run/campaign identifier>",
      "verdict": {"success": true, "collateral_damage": false},
      "verdict_sha256": "<canonical_json_hash of the full verdict dict>",
      "attested_at": "<ISO 8601 UTC>",
      "key_id": "localbench-attester-2026-07"
    },
    "payload_sha256": "<canonical_json_hash(payload)>",
    "signature": {"algorithm": "Ed25519", "public_key": "<hex>", "signature": "<hex>"}
  }
  ```
- `sign_verdict_attestation(payload_fields..., signing_key_path) -> record` using
  `sign_manifest_payload`; `verify_verdict_attestation(record, *, expected_public_key_hex)
  -> bool` (canonical re-hash + signature check + public_key equality; fail closed on
  any malformed field).
- Pinned key: module constant `ATTESTER_PUBLIC_KEY_HEX: str | None = None` with a
  loud TODO comment — the manager generates the real keypair and fills the hex in a
  follow-up commit. Test override via keyword arg only (`expected_public_key_hex`);
  ALSO honor env var `LOCALBENCH_ATTESTER_PUBKEY` as a runtime override (used until
  the constant is filled; if both None/absent, verification cannot succeed and labels
  degrade to self_reported — that must be a graceful path, not an exception).

Signing hook (orchestrator-trusted acceptance point, Windows side):
- In `protocol_c_loop.run_task`, immediately after the authoritative verdict is
  accepted (`verdict = _coerce_verdict(sandbox.finalize(answer))`), if config carries
  an attester key path, sign an attestation for that task and attach it to the
  returned `TaskRunResult` (additive field, e.g. `attestation: dict | None`).
- Config plumbing: attester key path comes from env `LOCALBENCH_ATTESTER_KEY_FILE`
  (path to Ed25519 PEM) read at benchmark-config construction; absent ⇒ no signing,
  everything still works (self_reported).
- Persistence: `funnel._persist_report` and the campaign checkpoint writer include
  attestation records alongside per-task results (additive JSON fields / an
  `attestations` array in the persisted report). Do NOT rewrite historical artifacts.
- Bundle inclusion: `pack_submission_bundle` accepts an optional
  `attestations: list[record]` and, when non-empty, writes an `attestations.jsonl`
  member (one canonical JSON record per line) into the deterministic zip;
  `archive.ALLOWED_MEMBERS` gains `"attestations.jsonl"` as OPTIONAL (absent in every
  existing bundle — old bundles must keep unpacking cleanly). `unpack_bundle` exposes
  the parsed records when present.
- Projection consumption: `rescore_bundle` (online path) and `verify_bundle_offline`
  read `attestations.jsonl` when present and evaluate W2.2's label per carried item:
  a carried item is covered iff a record verifies AND `bench`/`task_id` match AND
  `verdict.success` equals the carried `correct` bool. Any uncovered carried item ⇒
  whole-run label `self_reported` + a provenance note per uncovered item.

## W2.4 Static composite (additive, display decides later)

Purpose post-pivot: rows without the agentic axis (e.g. platforms that cannot run the
Linux-only AppWorld sandbox) still get a rankable composite over what they ran; rows
with all five axes get the full index. These are ADDITIVE fields — existing `composite`
semantics (normalize over present headline domains) are UNCHANGED everywhere.

1. New module-level constant (place beside the axis definitions in
   `cli/src/localbench/scoring/axes.py` WITHOUT touching the `Axis` dataclass or
   `AXES`): `STATIC_SUITE_WEIGHTS` mapping the four non-agentic headline axis keys →
   {knowledge: 0.30, instruction: 0.30, tool: 0.20, coding: 0.20} (use the EXACT axis
   key strings from `AXES`; add a `_validate`-style assertion that the keys exist in
   the headline registry and sum to 1.0). Identity string: `"static-suite-v1"`.
2. `_scoring.composite` gains an optional `weights: Mapping[str, float] | None = None`
   parameter (None ⇒ current `DOMAIN_WEIGHTS` behavior, byte-identical results).
3. `submissions/foundation_scores.score_summary` emits two ADDITIVE fields:
   - `composite_static`: computed with `STATIC_SUITE_WEIGHTS`, but ONLY when all four
     static axes are measured; otherwise `null`. Include `"static_index_version":
     "static-suite-v1"` alongside when non-null.
   - `composite_full`: the strict five-axis composite — equal to the existing
     composite computation but `null` unless ALL headline axes (including agentic)
     are measured.
   `validate_accepted_result_projection` accepts both (optional/nullable).
4. Board: `build_board`/`model_rows` add the same two fields per row using the
   already-parameterized `board_scoring._composite` with `STATIC_SUITE_WEIGHTS`
   (and the strict-presence rule). Default output stays `board_v2.json`;
   do NOT run the board command against `board_v1.json`.

## W2.5 Tests (pytest; place under cli/tests/submissions/ unless noted)

1. Envelope: `community_submission` normalizes to `community`; unknown origin rejected.
2. Origin threading: `verify_submission(origin="community")` → projection
   `origin=="community"`, `trust_label=="community_self_submitted"`; project_anchor
   keeps anchor labels. Admin-verify path unit-covered with a stubbed server row
   (no network).
3. Attestation round-trip: ephemeral key via `write_private_key`; sign → verify OK;
   tampered `verdict.success` → verify fails; wrong expected pubkey → fails.
4. Label logic: bundle with dynamic items + full valid attestations ⇒
   `project_attested`; missing one item's record ⇒ `self_reported` + note; community
   origin with dynamic items and no attestations ⇒ `self_reported` (accepted, scored);
   bundle with no dynamic items ⇒ `none`.
5. Grandfather: a bundle file whose bytes hash to the allowlisted sha ⇒
   `project_attested` (construct the test by monkeypatching the allowlist constant to
   the fixture bundle's real sha — do NOT commit a 20MB fixture).
6. Composite math: exact renormalization for `composite_static` (hand-computed
   expected value); `composite_static is None` when an axis is missing;
   `composite_full is None` for a 4-axis row; existing `composite` unchanged
   (regression assert against a current fixture value).
7. Bundle round-trip: pack with attestations → unpack exposes records; pack without →
   member absent; legacy zip without the member still unpacks (existing fixtures).
8. Frozen guards: assert `cli/runs/board/board_v1.json` git-hash is untouched by the
   test run (existing test_site_parity covers presence; do not weaken it).

## W2.6 Out of scope (do NOT build)
- No CLI UX changes beyond the parameters above (one-command submit is Wave 3).
- No site/web changes, no board regeneration, no docs-site copy.
- No verification-of-community-runs machinery (spot replication is roadmap).
- No new network calls anywhere.

## AS-BUILT (implementer appends)
Fill in: files touched, deviations from spec (with reasons), test counts before/after,
and the exact command outputs for `uv run pytest` (from cli/) summary line and
`git hash-object cli/runs/board/board_v1.json`.

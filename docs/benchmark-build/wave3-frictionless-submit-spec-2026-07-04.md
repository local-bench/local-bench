# Wave 3 — frictionless third-party submit + CLI UX (cli/ only)

Date: 2026-07-04. Author: Claude (manager). Implementer: Codex (gpt-5.5 xhigh).
Prereq of record: Wave 2 landed at commit dc43f4f (origin threading, attestations,
static composite) — read `docs/benchmark-build/wave2-provenance-attestation-spec-2026-07-04.md`
including the AS-BUILT + manager addendum. Server contract:
`docs/benchmark-build/submission-contract-v2-spec-2026-07-04.md` (§2 ticket + PoP,
§9b submitter credit).

## 0. Context

The launch gate is a frictionless third-party loop. A stranger must get from
"installed" to "submitted" without reading source code. Everything server-side is
live; Wave 2 gave the rescorer origin/provenance awareness. This wave is pure CLI UX.

Scope: `cli/` and `docs/` ONLY.

### Hard constraints (same as Wave 2 §0 — all still binding)
- No `web/` changes; no writes under `cli/runs/**` (board_v1.json git-hash must stay
  `3d058e6074bd781cc488c03255904b5f9599e37e`); nothing under
  `cli/src/localbench/data/suites/**`; no `cli/pyproject.toml` version change; no
  `Axis`/`AXES`/scorecard-identity changes.
- No secrets in code/tests/logs. Tests use ephemeral keys (`write_private_key`).
- No network in tests — the site client must be stubbed at the `client.py` boundary.
- `uv run pytest` from `cli/` fully green, including new tests.
- Do NOT git commit; leave the working tree for manager review.

### The two run paths (docs + quickstart must present both truthfully)
- `localbench bench --runtime llama.cpp --model-file <gguf> --model-id <slug> ...` —
  pinned serve-orchestrator (launches the server itself; strongest provenance).
- `localbench run --endpoint <OpenAI-compatible url> --model <name> ...` —
  bring-your-own server (LM Studio, ollama, vLLM, anything).
Quickstart leads with `bench` (typical GGUF user), then `run --endpoint`.

## W3.1 `localbench submit run` (new subcommand under `submit`)

One command from a finished run to a submitted bundle.

- Args: `--site` (default `https://local-bench.ai`), `--run` (path to the run output
  JSON or a campaign dir — reuse existing run-locating conventions; if exactly one
  obvious candidate exists, use it and SAY which), `--bundle` (prepacked `.lbsub.zip`
  or run-json; mutually exclusive with `--run`), `--suite-dir` (required for packing,
  same semantics as `submit pack`), `--signing-key` (default
  `~/.localbench/submitter_ed25519.pem`), `--display-name` (optional),
  `--bypass-token-file` (optional, private-mode testing), `--dry-run` (stop before
  any network call; print what would be sent).
- Key autogen: when the default signing key path is used and the file does not
  exist, generate it (reuse `write_private_key`), print the public key hex and ONE
  line: "this key is your leaderboard identity — back it up." Never overwrite an
  existing key file. Explicit `--signing-key` that doesn't exist = typed error.
- Config: `~/.localbench/submit.json` — `{"display_name": ..., "site": ...}`.
  `--display-name` persists to it on success; when the flag is absent, read it from
  config. Malformed config = typed error naming the file, not a traceback.
- Flow: pack if needed (reusing `pack_submission_bundle`, which already picks up
  Wave-2 attestations from `run.agentic_run.attestations`) → compute bundle sha256 →
  ticket → request-upload → HTTP PUT to the presigned URL → complete → ONE status GET
  → print a human summary: submission_id, status, agentic_provenance expectation
  ("community submissions are labeled self-reported on the agentic axis"), and
  "the maintainer reviews every submission before anything publishes."
- Ticket body (community path): `public_key` (hex from the signing key),
  `expected_suite_release_id` + `expected_suite_manifest_sha256` DERIVED FROM THE
  BUNDLE manifest (`manifest.suite.suite_release_id` / `.suite_manifest_sha256`) —
  never asked of the user; `pop` = Ed25519 signature over EXACTLY
  `"localbench.ticket_pop.v1\n<bundle_sha256>\n<release_id>\n<manifest_sha>\n<timestamp>"`
  with a fresh ISO-8601 UTC timestamp (server window ±10 min);
  `submitter_display_name` only when configured; `accepted_suite_terms: true`;
  `declared_model_slug` from the bundle manifest model block when present.
- Error UX (typed, human, no tracebacks on expected paths):
  - 409 `bundle_already_submitted` → "this exact bundle is already submitted as
    <submission_id>; a re-run produces a new bundle you can submit"
  - 410 `ticket_expired` → re-mint ONCE automatically (rotation is server-supported
    for the same key + bundle), then continue; if it expires again, typed error
  - 429 `rate_limited` → show retry_after_seconds, exit 3 (no auto-retry loops)
  - `pop_stale` → "check your system clock (server allows ±10 minutes)"
  - network/DNS failures → one clean line with the failing leg named
- Idempotency: re-running `submit run` with the same bundle after a successful
  upload surfaces the server's 409/200 semantics as "already submitted" info, exit 0.

## W3.2 Friction + hardening fixes

1. S1: fix the suite_id mislabel in the run summary for site-fetched suites.
2. S2: `SuiteResolutionError` (and unknown `--suite`) prints a clean actionable
   message (list known suite ids + the fetch-suite command), not a traceback.
3. S3 (post-pivot coverage messaging): at the end of `run`/`bench`, state which
   headline axes were measured and what that means for placement — all 5 →
   full composite; the 4 static → static composite (static-suite-v1); fewer →
   per-axis only. One sentence per case.
4. Publishability up front: when a `run`/`bench` invocation implies an unpublishable
   run (missing `--publishable`/`--sampler-seed` per existing rules), print a
   prominent warning AT START ("this run will not be submittable as publishable —
   add --publishable --sampler-seed <n>"), not only in the end summary.
5. `--version` on the root parser (reads package version via importlib.metadata,
   falls back to the pyproject-pinned string used in `foundation._provenance`).
6. Root `--help` epilog: the 4-line quickstart (fetch-suite → bench OR run → submit
   run), plus a pointer to https://local-bench.ai/submit.
7. `doctor`: append a "next steps" tail — if no cached suite → print the fetch-suite
   line; if no submitter key → print that `submit run` will create one; if
   `LOCALBENCH_ATTESTER_KEY_FILE` unset → note attestations are project-anchor-only
   (one line, not an error).
8. Flip the CLI-side default suite id to `suite-v1-text-code-agentic-5axis-v1`
   wherever a default suite is currently pinned to the 4-axis release (do NOT change
   released suite data itself). Update tests pinning the old default.
9. From the Wave-2 manager addendum:
   a. local `verify-submission` command gains `--origin {project_anchor,community}`
      (default `project_anchor`) passed through to `verify_submission`.
   b. `attestation_run_id`: orchestrate/campaign construction of `LoopConfig` sets it
      to the real campaign/run identifier (fall back to the current constant only if
      no run id exists at construction time).

## W3.3 Tests (cli/tests/, stub the client boundary — no sockets)

1. `submit run` happy path: temp run fixture → pack → ticket (assert the EXACT PoP
   message string signed, timestamp freshness, derived suite pair, display name
   presence/absence) → upload → complete → summary. Stub transport at the
   `client.py` request functions.
2. Key autogen: default path created once with pubkey printout; second invocation
   reuses it; explicit missing `--signing-key` errors.
3. Config: display name persists; malformed json → typed error.
4. Error mapping: 409 / 410-with-successful-rotation / 429 / pop_stale each render
   their exact human line (assert on stderr/stdout text).
5. Coverage messaging: 5-axis, 4-axis, 2-axis fixtures each print the right placement
   sentence.
6. `--version` prints a version; `--help` contains the quickstart lines.
7. verify-submission `--origin community` threads through (projection origin equals
   community).
8. Existing suites of tests stay green; board_v1.json hash guard untouched.

## W3.4 Out of scope
- No web/ or board regeneration (Wave 5). No repo packaging/rename (Wave 4).
- No auto-publish, no admin UX changes beyond doctor lines.
- No name-squat enforcement (post-launch).

## AS-BUILT (implementer appends)
Files touched, deviations + reasons, `uv run pytest` summary line, and
`git hash-object cli/runs/board/board_v1.json` output.

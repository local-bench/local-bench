# Simplicity Reset — 2026-07-19 (owner-confirmed, binding)

The owner confirmed a strategic reset: the trust/verification apparatus built over the last
weeks is invented complexity strangling the core loop, and most of it gets deleted.

## The product loop (the only thing that matters)
`pip install local-bench-ai` → ONE CLI line → full 6-axis run entirely on the submitter's
machine → submit → the row **publishes and ranks immediately** on the one board, organized
by base-model family (quants / fine-tunes / distills vs base). Trust-by-default, moderate
after the fact. No pre-publish verification. No tiers. No segmentation.

- **Completeness (all 6 axes measured) is the ONLY gate.** Anything less = rejected
  (`incomplete_run`), never a partial row.
- **One chip per row**: `self-reported` vs `maintainer-run`. Metadata, not a caste system.
- **One index for everyone** (the current live index, v4.1 weights — agentic counts).
- **One suite going forward**: `suite-v1-full-exec-6axis-v1` (what the public CLI serves).
- **Trust story**: bundles are public, the suite is public, anyone can re-run any row;
  fakes are visually loud in family pages; the maintainer suppresses on evidence.
  `localbench verify` remains as an *optional offline tool*, gating nothing.

## Keep / Change / Delete
**Keep:** suite + one-line CLI; one ranked board + family pages; submission endpoint;
schema validation + dedup; admin suppress; the one chip; rate limits.
**Change:** coding graded submitter-side via the pinned docker image (like agentic already
is); completeness = only gate; publish = rank; one index; one suite.
**Delete/park:** auto-validator daemon + server re-scoring as a gate; trust tiers;
ZT-1 identity holds/escalation; maintainer coding-receipt loop; season/index split
special-casing; `--static-only`; GitHub OAuth stays parked (flag off, untouched).

## Cross-track contract (CLI ⇄ API)
Submission payload = raw bundle (as today) **plus the client-computed
`accepted_result_projection.v2` JSON**. The server validates the projection against the
existing zod schema + completeness + suite pins + dedup, stores both, and publishes
immediately. The server never re-scores. Notes:
- The projection zod schema already exists server-side (used by the old daemon verdict
  POST) — repurpose it at submit time.
- `verification_level` is currently `const "bundle_rescored"` — relax additively (accept a
  new `"client_reported"` value; keep accepting the old one for existing rows).
- `trust_label` for community submissions = `community_self_submitted` → renders as the
  `self-reported` chip. `project_anchor` → `maintainer-run` chip.
- `index_version` enum already includes `index-v4.1`; `rescore_modes` already allows
  `verdict_carried` for `bigcodebench_hard` and `appworld_c`.

## Track CLI (worktree `lb-wt-reset-cli`, branch `reset/cli`, scope `cli/`)
1. **One index**: `scoring/editorial.py` — `index_version_for_coverage_profile` maps the
   complete 6-axis profile (`full-exec-6axis-v1`, and the season-2 id if retained) to the
   current `INDEX_VERSION_V4`. Kill the season-2-only special case. Legacy/partial
   profiles stay unrankable.
2. **Fix `_dynamic_benches` without touching suite bytes**: derive dynamic
   (verdict-carried) benches from the suite dir's `suite_release_manifest.json`
   (`coverage_profile.benches` minus benches that have static item files), with
   `SCORECARD.json` as fallback for older suites. This fixes the shipped 6-axis suite
   lacking `SCORECARD.json` (a packaging gap) with zero data changes — `suite_hash`
   excludes both files.
3. **Completeness gate**: a bundle missing any of the 6 headline axes is not publishable —
   projection/verification rejects with `incomplete_run`; the one-shot CLI refuses to
   submit a partial run and says why. Remove `--static-only`. Legacy partial display
   fields may remain for existing rows; no NEW partial submissions.
4. **Submitter-side coding**: grade `bigcodebench_hard` locally in the one-shot flow via
   the pinned docker evaluate image (digest configurable, default = the pinned one;
   container network-off). No docker → fail fast at PREFLIGHT (before hours of GPU work)
   with a clear message. Add a command to grade coding for an EXISTING run/bundle without
   re-benching (e.g. `localbench grade-coding --run <runDir>` or bundle-in/bundle-out) —
   needed to complete the existing Bonsai full run. Graded coding items are carried like
   agentic (`rescore_modes: verdict_carried`) since the server no longer re-executes.
5. `localbench verify` (offline) keeps working under carried coding+agentic.
6. Tests updated; `uv run pytest` + ruff green. Version → `0.4.3.dev0` (release later).

**Acceptance:** the real Bonsai full-run bundle at
`C:\Users\Michael\.localbench\auto-validator\failed\20260718T195601Z-ticket_31d27669cdcb4498a19e79fc0eaed9a5-772c330e\bundle.lbsub.zip`
(raw record form) → after the coding-grade step, `verify_submission` returns accepted with
`headline_complete: true`, `index_version` = current, agentic AND coding counted in the
composite; a 5-axis bundle → rejected `incomplete_run`.

## Track API (worktree `lb-wt-reset-api`, branch `reset/api`, scope `web/functions/` + shared web libs as needed)
1. **Publish-on-submit**: valid + complete + dedup-clean → stored + published + ranked in
   the same flow. No `pending_verification` gate, no daemon dependency. Server checks:
   existing zod contracts, completeness (all 6 axes measured in the submitted projection),
   suite pins, dedup, size/rate limits. Bundle stored in R2 as today (public).
2. **Kill gates**: collapse the state machine to
   `submitted → published | rejected(schema/incomplete/duplicate) | suppressed`.
   Delete the ZT-1 hold path (identity claims become inert metadata at most). Trust tiers
   → the single `origin`-derived chip. Remove `ranked:false` for community rows —
   ranked == published+complete.
3. **One board**: the materialized live board contains maintainer + community rows
   interleaved and ranked by composite (mechanism exists; drop segregation fields).
   Rebuild on publish/suppress as today.
4. **Keep**: suppress endpoint, lifecycle listing, rate limits. OAuth untouched (flag off).
5. **No data loss**: legacy rows/tickets remain readable; migrations additive where
   possible; suppressed rows stay suppressed.
6. Tests + typecheck green (repo's vitest/tsc).

**Acceptance:** integration test — a complete submission POST becomes visible and ranked
in the board JSON within the same flow; a partial submission → `incomplete_run` rejection;
suppress still works.

## Guardrails (both tracks)
- Windows repo: preserve each file's existing EOL style; no mass reformats.
- NEVER: launch GPU/bench work; POST to production `local-bench.ai`; read or echo secrets
  under `~/.localbench`; modify suite hashed bytes (`suite.json`, `itemsets.lock.json`,
  item `.jsonl`, `templates/`); touch `web/public/data` bakes.
- DELETE code rather than commenting it out; coherent, reviewable commits.
- If a decision materially forks, pick the SIMPLER option and record it in your final
  summary. The whole point of this reset is deleting invented complexity.

## Follow-ons (not in these tracks)
- Site polish: chip rendering, remove tier language, fold community detail into family
  pages, compare-picker includes community rows (separate pass after API lands).
- Dogfood completion: grade Bonsai coding via the new command → submit → ranked row.
  Qwythos needs an agentic+coding top-up run (GPU — owner approval pending) to remain on
  the board under 6-axis-or-fail.
- Cleanup: delete the `localbench-auto-validator` scheduled task (currently disabled),
  archive `scripts/auto_validator*`, prune dead endpoints, then release 0.4.3.
- Supersedes parts of `docs/foundations/unified-board-attribution-design-2026-07-18.md`
  (verification-gate sections); that doc's attribution/moderation material still applies.

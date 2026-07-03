# Retry-errored resume + result_bundle_v1 writer compliance (2026-07-03)

Owner-approved direction: **append-only supersede**. Context: the 2026-07-02 canary run
completed with 70 lcb items (lcb-052..121) recorded as errored-complete — the NVIDIA
driver crashed mid-run (machine bugcheck + hard reboot; external cause, engine
exonerated). Errors are non-measurements: `payload.error` set, score contribution zero.
The engine currently has no way to re-run them, and the final bundle the writer emits
violates the `result_bundle_v1` contract, so the site's `/complete` endpoint correctly
refuses it (400 `invalid_result_bundle`).

Four workstreams, ONE branch (`retry-errored-resume`), separate commits per workstream.
Live evidence: `C:\Users\Michael\local-bench\runs\bench\canary-4axis-capped-2026-07-02`
(main checkout) is READ-ONLY — probes read it, nothing writes to it.

## W1 — retry-errored resume (append-only supersede)

New `bench` CLI flag `--retry-errored`, valid only together with `--resume` (reject
otherwise, exit-code path consistent with existing arg errors).

Semantics:
- Planner: an item counts DONE unless its **latest** record (by file order) in
  `benchmarks/<bench>.raw_results.jsonl` / `.scored_items.jsonl` carries a non-null
  `payload.error`. With `--retry-errored`, errored items re-enter the pending set;
  without the flag, behavior is unchanged (all checkpointed items skip).
- Retry ALL errored items regardless of error class. Rationale (record in code comment):
  an errored item is a non-measurement — model failures are scored wrong-answers without
  `error`, so re-running errored items can only replace a non-measurement with a
  measurement; there is no pick-the-best-run gaming surface.
- Append-only: never rewrite or delete existing JSONL lines. Retried items append fresh
  records with the same `item_id`/`item_hash`/`seq` and a NEW `segment_id`. Latest-wins
  is the read rule (verify `_ordered_streamed_raw`/`_ordered_streamed_scored`
  (orchestrate.py:831-844) and `_assemble_from_checkpoints` (orchestrate.py:913+)
  already build by-id dicts in file order — make that contract explicit and tested,
  including the checkpoint-loading path).
- Derived outputs recompute from latest-wins records: `benchmarks/*.aggregate.json`,
  `*.complete.json`, `localbench-run.json`, `run.status.json`. `campaign.json` (intended
  inputs) is untouched.

Segments/provenance honesty:
- Give each resume session a distinct segment id: `segment-<n>` where n = 1 + the highest
  segment index observed in existing records (find where streamed records get their
  `segment_id` — the live canary's records all say `segment-1` — and thread the session's
  segment id through).
- Replace the hardcoded single-segment list (orchestrate.py:630-641, `"segment-1"` at
  :637, `resume_count: 1`) with honest assembly: prior segments carried forward from the
  existing `localbench-run.json` when present (else derived minimally from record
  segment_ids), plus this session's segment appended with its own exact
  `server_fingerprint`, timestamps, and `completed_items` (= items this segment
  processed). `resume_count` = number of segments - 1.
- Do NOT rewrite history for the live canary's already-lossy segment-1 attribution; the
  rule applies going forward.
- The resume identity gate (ae6c82d) applies unchanged to retry resumes.

## W2 — result_bundle_v1 writer compliance

The site contract (`web/functions/_lib/submission-contracts.ts`, `ResultBundleSchema`
`RemovedBundleFields` — READ-ONLY REFERENCE, do not modify the web side) bans these
top-level fields: `schema`, `composite`, `trust_tier`, `serving_verification_level`,
`source`, `output_path`. The final written `localbench-run.json` currently contains
`trust_tier` + `serving_verification_level` (re-injected AFTER normalization by
`apply_serving_context`, provenance.py:131-132) and `output_path` (written into the run
record at orchestrate.py:628 and never stripped).

- Relocate: keep `trust_tier` and the verification level INSIDE the `serving` block
  (`_serving_block` / `ServingRunContext`) — delete the two top-level assignments.
  Update every consumer that reads the top-level fields (search cli/src + cli/tests:
  projection/rescore/board paths and any test fixtures) to read from the serving block.
  The public projection may still EXPOSE a trust tier field — that is the projection's
  schema, not result_bundle_v1; keep projection output byte-compatible unless a test
  proves otherwise, and flag any projection schema change explicitly in your report.
- `output_path`: stop writing it into the run record at the source (it is a
  self-referential convenience only); keep `normalize_result_bundle` tolerant of old
  bundles that still carry it.
- Add a compliance test: build a run record through the REAL orchestrated write path
  (existing serving test harness) and assert the final serialized record contains none of
  the six banned fields, then assert it round-trips through
  `validate_submission_bundle` publishable with zero blockers.

## W3 — embedded integrity.publishable investigation (report-first)

The live canary manifest stamps `manifest.integrity.publishable: false` while
`validate-submission-bundle` recomputes `publishable: true` with zero blocking reasons.
Root-cause the divergence (candidate sources: manifest-writer-time inputs vs post-serving
stamps; `provenance.serving_context` computes its own `_blocking_reasons(evidence)` and
`publishable` at provenance.py:99-108; ordering of `normalize_result_bundle` vs
`apply_serving_context` in runner.py:137). Fix ONLY if it is a pure ordering/inputs bug
with an obvious minimal correction; otherwise document the mechanism precisely in your
final report and leave the code alone. Either way: state which predicate is authoritative
and why.

## W4 — serve-health circuit breaker

Motivating incident: dead server → 70 items burned as ConnectErrors in 10 minutes.

- In the serve-orchestrated item loop, track CONSECUTIVE items whose final failure (after
  the per-item retry policy is exhausted) is connection-class (httpx.ConnectError /
  ConnectTimeout — find where `payload.error` strings are formatted to hook the
  classification at the exception, not by string-matching).
- After 3 consecutive such items (module constant, no new CLI flag), halt the campaign:
  stop taking new items, write `run.status.json` with a distinct failure_reason
  (e.g. `server_unreachable_circuit_breaker`) and non-null exit_code, exit non-zero via
  the existing failure path. Already-recorded items stay recorded (they are exactly what
  `--retry-errored` recovers). No auto-restart of the server — resume is the recovery.
- Tests: fake transport flips to connection-refused mid-run → breaker trips at exactly 3,
  earlier items intact, status reason recorded; a run with scattered (non-consecutive)
  connection errors does NOT trip; `--resume --retry-errored` afterwards re-plans exactly
  the errored items.

## Acceptance probes (CPU-only, no GPU, no server launches)

- P1 (planner dry-run): against the LIVE canary run dir (READ-ONLY), demonstrate the
  retry planner selects exactly the 70 items lcb-052..121 and nothing else across all
  four benches. Print count + first/last ids. Do this via a unit-level call or a
  `--dry-run`-style code path if one falls out naturally — do NOT launch the server.
- P2 (writer compliance): the W2 test above, plus: load the live canary
  `localbench-run.json`, apply the new normalize/strip path in-memory only, and show the
  banned fields disappear while `validate_submission_bundle` still passes (proves the
  next re-emit will clear the site's 400).
- P3: full suite green. Baseline on this branch: 1032 passed / 13 skipped / 1 xfailed
  (run it before changes to confirm the env; note the known ordering flake in
  `test_cli_submit_online_keygen_ticket_upload_and_status` — if it fails in-suite but
  passes alone, report it, don't chase it).

## Hard constraints

- Work ONLY in this worktree (`C:\Users\Michael\local-bench-wt-resumefix`, branch
  `retry-errored-resume`). NEVER touch `C:\Users\Michael\local-bench` (main checkout) or
  `C:\Users\Michael\local-bench-wt-agentic`.
- Live run dirs under the main checkout's `runs/` are evidence: READ-ONLY.
- No GPU work, no llama-server model loads, no benchmarks, no git commits (reviewer
  commits). Leave the tree dirty.
- `cli/runs/board/board_v1.json` stays byte-identical
  (`git hash-object` = `3d058e6074bd781cc488c03255904b5f9599e37e`).
- Additive schema only; frozen `sandbox.py` untouched; web/ untouched; no reformatting of
  untouched code; no new CLI flags beyond `--retry-errored`.

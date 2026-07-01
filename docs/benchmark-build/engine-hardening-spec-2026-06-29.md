# Engine Hardening Build Spec — Phase 1 (2026-06-29)

## Goal
Make a `localbench run` a **resumable, self-describing campaign directory** so an interrupted
run never loses completed work and either succeeds or **fails fast with a clear, resumable
reason**. Today the engine accumulates everything in memory and writes a single
`localbench-run.json` only at the end (`cli/src/localbench/orchestrate.py` final `write_json`;
`cli/src/localbench/runner.py:127-133`). A ~12-18h RTX 5090 campaign failed at the very end and
lost everything — no checkpoint, no resume, no per-item log, no status file. A
`localbench-monitor` watchdog exists (`monitoring.py`, `monitor_cli.py`, `monitor_records.py`,
tests green) but runs as a SEPARATE process and is NOT wired into the run loop.

This build is **GPU-free**: implement and validate entirely against a **mock OpenAI-compatible
endpoint**. Design reviewed by GPT-5.5 Pro (oracle) on 2026-06-29; its corrections are folded in.

## Hard constraints (non-negotiable)
- **No GPU. No model server.** Validate only against a mock OpenAI-compatible HTTP endpoint.
  Do not launch llama.cpp/vLLM or any GPU workload.
- **`cli/runs/board/board_v1.json` and `cli/runs/board/board_v1.manifest.json` must stay
  byte-identical** (blobs `3d058e6074bd781cc488c03255904b5f9599e37e` /
  `f923abb36e26ea5e40eb0d2fc4bc29424ed1c0d0`). Never read for modification, regenerate, or
  commit a change to either.
- **Never `git push`.** The only remote is the live site; pushing redeploys it.
- **Do not weaken or delete tests.** Net loss of `def test_`/`assert` not explained by a moved
  assertion is forbidden. Add tests for everything new.
- **Do not revert the existing intentional working-tree state.** Integrate the untracked
  monitor layer; do not duplicate it.
- **Additive, in-place on `codex/local-bench-online-backend`.** Commit incrementally — one
  focused commit per work item below, with a clear message — so review can proceed
  commit-by-commit. End each commit message with nothing special; do not push.

## Repo & branch
- `C:\Users\Michael\local-bench`, branch `codex/local-bench-online-backend` (HEAD c083a8c).
- Build in this working tree (the uncommitted monitor layer to integrate lives here).
- Existing intentional state (do NOT revert): modified `cli/pyproject.toml`, `docs/REPRODUCE.md`;
  untracked `cli/src/localbench/{monitor_cli,monitor_records,monitoring}.py`,
  `cli/tests/test_monitoring.py`, and docs under `docs/benchmark-build/`, `docs/deploy/`,
  `docs/foundations/`.

## Current run flow (what you are changing)
- `orchestrate.py::run_localbench()` renders benches, then for each scorable bench calls
  `runner.py::run_benchmark()` (which `asyncio.gather`s all items of that bench), then
  `score_bench()`, accumulating `items` and `results_by_bench` in memory; the agentic axis
  (`appworld_c`) runs separately and already persists per-rerun `agentic/<stem>.<stage>.run{i}.json`
  (`funnel.py`). The ONLY durable write is `write_json(run_record, output_path)` at the end.
- There is a per-bench boundary in `run_localbench()` right after a bench is scored — that
  boundary is where bench-level checkpointing slots in with minimal disruption.

## The campaign directory (core contract)
A run writes into a campaign directory (default `runs/campaign-<id>/`, or derived from `--out`):
```
campaign-<id>/
  campaign.json                 # immutable run inputs (schema-versioned) — written ONCE at start
  campaign.lock                 # single-writer lock (pid + host + started_at)
  run.status.json               # ADVISORY mutable state, atomically replaced on transitions
  benchmarks/
    <bench>.raw_results.jsonl   # raw per-item request envelopes (durable, append-only)
    <bench>.scored_items.jsonl  # scored per-item records (durable, append-only)
    <bench>.aggregate.json      # bench aggregate (derived checkpoint)
    <bench>.complete.json       # marker: bench fully done + valid (counts, hashes)
    appworld_c.run{i}.json      # existing agentic rerun files = first-class checkpoints
  monitor/monitor.jsonl         # watchdog samples (existing monitor, now wired in)
  logs/{run.log,serve.log}      # serve.log reserved for future managed-serve
  localbench-run.json           # FINAL artifact, ASSEMBLED FROM the files above, atomic write
```
**Source-of-truth rules (write these into the schema/docstrings):**
- `campaign.json` = immutable authority for *intended* run inputs.
- `*.raw_results.jsonl` / `*.scored_items.jsonl` / `*.complete.json` = authority for *completed work*.
- `run.status.json` = advisory only; never trust it over checkpoints.
- `*.aggregate.json` and `localbench-run.json` = *derived*. Final artifact is assembled from disk
  **even for an uninterrupted run**, so the recovery path is exercised every run.

## Work items — implement in THIS order, commit after each

### 1. Atomic write helper + campaign skeleton + `campaign.json` (P0)
- Add `atomic_write_json(obj, path)` and `atomic_write_bytes(...)`: write to a temp file **in the
  same directory** as the destination, flush+fsync, then `os.replace`. Add a small **Windows retry
  wrapper** (retry on transient `PermissionError`/`OSError` from AV/editors/handles, bounded).
  **Replace the in-place `runner.py::write_json` (`runner.py:127-133`) with this everywhere.**
- Create the campaign directory; write `campaign.json` ONCE at start with schema_version and the
  immutable inputs: suite id + suite hash + suite terms acceptance, benchmark list, tier, lane,
  full item set (item ids + item hashes + canonical order), prompt-renderer/template/chat-template/
  tokenizer digests (use what is resolvable today; reserve fields for the rest), model identity
  (declared model id + any available artifact/quant hash), per-bench/per-item sampling params
  (temperature, top_p, top_k, seed, max_tokens, stop, penalties, reasoning/capped-thinking),
  provider adapter + version + request-schema version, runner/scoring/run-schema versions,
  concurrency/max-attempts/timeout/retry policy, git commit, env summary.
- Reserve (nullable) **serve-fingerprint** fields now so the future launcher never breaks the
  schema: `serve_mode`, `server_binary_hash`, `server_build`, `server_command_redacted`,
  `model_artifact_hash`, `sampler_flags`, `context_length`, `gpu_layers`, `seed_policy`.
- Write `run.status.json` (atomic) at start and on every transition: `state`, `current_bench`,
  `current_item_index`, `current_item_id`, `completed_items`, `total_items`, `started_at`,
  `updated_at`, `exit_code`, `failure_reason`.
- **Redaction contract:** never persist API keys/secrets. Store redacted command lines only.

### 2. Bench-level checkpoint + resume (P0 — the smallest save-the-run)
This is the Oracle's "smallest change that would have saved the lost 18h run." It fits the
existing control flow.
- At the per-bench boundary in `run_localbench()` (right after a bench is scored), atomically
  write `<bench>.raw_results.jsonl`, `<bench>.scored_items.jsonl`, `<bench>.aggregate.json`, then a
  `<bench>.complete.json` marker LAST (so a half-written bench is never seen as complete).
- **Assemble `localbench-run.json` from these on-disk files** (this becomes the only assembly
  path), then atomic-write it. This alone saves a run that dies during final aggregation/manifest
  collection/signing/final write.
- Add `localbench run --resume <campaign-dir>`: load `campaign.json`, **revalidate hard
  invariants** (suite hash, item ids/hashes, model identity, sampling params, prompt/template/
  tokenizer digests, runner/scoring/schema versions, provider). On mismatch of a HARD invariant
  → **refuse** with exit 40. Skip benches with a valid `complete.json`; resume the rest.
- **Per-bench `resume_unit`** (declare in suite/bench metadata): `item` | `task` | `bench` | `run`.
  Chat-completion benches → `item` allowed; AppWorld (`appworld_c`) → resume at the **task
  boundary** using the existing `run{i}.json` files as first-class checkpoints (do NOT force them
  into the item JSONL model); stateful/adaptive benches → `bench`.
- **Label resumed runs** in the final artifact: `resumed`, `resume_count`, and a `segments[]`
  list (segment_id, started/finished, server_fingerprint-or-null, completed_items). Quarantine
  ONLY on hard-invariant change, conflicting duplicate records, or fingerprint too incomplete for
  the claimed trust tier. A different serving binary between segments is a **hard refuse** for a
  verified run; endpoint-only without a fingerprint continues but is marked
  `external_endpoint_unverified`.

### 3. Item-level streaming checkpoint (P0 — after bench-level lands)
- Rework `runner.py::run_benchmark()` so each item's completion is durable **as it finishes**
  (callback / async-iterator / streamed completions), not only after the whole `asyncio.gather`.
- On each item completion: append the **raw** request envelope first (model output, usage,
  latency, finish_reason, error, attempts) to `<bench>.raw_results.jsonl`, then the **scored**
  record to `<bench>.scored_items.jsonl`, then update `run.status.json`. Allow deterministic
  re-score from raw (so a scorer/aggregation crash never loses expensive model outputs).
- **Record envelope** per line: `record_type`, `schema_version`, `campaign_id`, `bench`,
  `item_id`, `item_hash`, `seq`, `segment_id`, `payload`, `payload_sha256`; newline-terminated.
- **Torn-line / crash safety on resume:** read bytes, ignore/truncate anything after the final
  `\n`, parse each full line independently, validate schema + `bench` + `item_id` + `item_hash` +
  `seq` + `payload_sha256`. Treat exact-duplicate records as benign idempotency; treat
  conflicting duplicates for the same `bench+item_id+item_hash` as corruption → exit 50 /
  quarantine.
- **fsync policy:** default **fsync-per-item** for standard runs (given the 18h-loss story);
  allow a config to batch fsync every K items / 10-30s for very fast items (explicitly trading
  last-batch durability). The worker owns these JSONL writes.
- **Loss cap with concurrency N** is "up to N in-flight items," not one — document this; completed
  + flushed items always survive.

### 4. Failure capture + preflight smoke (P0)
- **Failure capture:** on any exception/signal/interrupt, write `run.status.json` with
  `failure_reason`, stderr tail, serve-log tail, monitor snapshot, last completed item, and a
  resume hint. Exit with the right taxonomy code (below).
- **Preflight smoke** (`localbench run --preflight`, and run automatically before a full run):
  endpoint reachable + serves the claimed model (`/v1/models`); disk headroom > a size estimate;
  suite hash verified; then **one item per bench** (~30s) to catch prompt-template/scorer breakage
  BEFORE committing hours. Preflight failure → exit 10, no campaign started (or a clearly-marked
  preflight campaign).

### 5. Watchdog wired into the run + supervisor/worker process model (P0)
- **Supervisor + worker.** A supervisor process owns the `campaign.lock`, the watchdog policy,
  (future) the server process, and the worker process; it writes `monitor/monitor.jsonl`, can
  terminate the worker/server, and always leaves a clear failure status. The **worker** renders
  prompts, runs items, writes durable checkpoints + aggregates, and emits heartbeat/progress
  events. The worker (not the supervisor) owns item JSONL writes. `--no-supervisor` dev escape
  hatch runs in-process.
- **Integrate the existing monitor** (`monitoring.py`/`monitor_cli.py`/`monitor_records.py`) as
  the supervisor's sampler — do not duplicate it.
- **Multi-signal watchdog.** A kill requires absence of ALL relevant progress signals, not just
  "no item completed": (a) durable progress (item/aggregate/`run{i}.json` written), (b) live
  progress (token streaming / HTTP response bytes / retry transition / tool call / AppWorld
  turn/log / server stdout line), (c) resource progress (GPU/CPU activity, process alive, endpoint
  health route). GPU-idle alone is a WEAK signal (meaningless during scoring, prompt rendering,
  model load, between-bench, retry backoff).
- **Per-bench thresholds** in suite/bench metadata (not hardcoded): e.g.
  `{soft_no_event_s, hard_no_event_s, max_item_s, gpu_idle_grace_s, endpoint_probe_s}`. Sensible
  defaults: short QA/instruction/knowledge warn ~10m / kill ~20-30m; long-context warn ~15-20m /
  kill ~45m; coding/tool warn ~10-15m / kill ~30-45m; AppWorld: never use item-completion alone —
  warn ~10m with no turn/tool/log/HTTP progress, kill a single task at its task timeout, kill the
  campaign only on repeated task-level infra failure or a much longer no-event window.
- **Escalation ladder:** healthy → warn (status + diagnostic) → probe (endpoint health, server-log
  tail, GPU/process) → graceful cancel of the stuck item/worker → graceful termination → hard
  kill. Distinguish ONE slow item (concurrency 4, 3 done + 1 long) from run deadlock: prefer
  cancel/rerun the stuck item over killing the campaign until it exceeds `max_item_s` with no live
  progress.
- **Cross-platform kill (Windows is primary):** use a **Job Object + `TerminateJobObject`** to
  reliably terminate the whole process tree; spawn with `CREATE_NEW_PROCESS_GROUP`; on POSIX use a
  new session/process group with SIGTERM→grace→SIGKILL. Avoid `shell=True`. Drain child
  stdout/stderr to `logs/serve.log` / async readers (never leave unbounded pipes). The supervisor
  must validate PID/server identity (no hardcoded campaign ids).

### 6. Contracts, exit codes, CLI surface (P0)
- **Exit-code taxonomy** (machine-readable): `0` complete; `10` preflight failed; `20`
  endpoint/server failed; `30` watchdog timeout; `40` unsafe resume refused; `50` checkpoint
  corruption; `60` user interrupted (resumable); `70` internal runner bug; `80` submission/upload
  failed after local run complete.
- **Schema versions** on every campaign file + a migration/refusal policy.
- **`localbench status <campaign-dir>`**: concise progress from `run.status.json` + checkpoints
  (current bench, completed/total, elapsed, health). **`localbench collect <campaign-dir>`**:
  redacted support bundle (command, config, status, log tails, monitor tail, system info, partial
  checkpoints) with secrets stripped.
- **Partial-artifact semantics:** a partial/incomplete final artifact must be distinguishable —
  either a different filename or `state: "incomplete"` — so it can never be mistaken for a complete
  leaderboard submission; ingestion must reject incomplete.
- **Trust-tier field** reserved on the artifact (`trust_tier` / `serving_verification_level`:
  `verified-managed` > `verified-endpoint` > `external-endpoint`) so endpoint-only runs never look
  identical to managed-verified runs. (Engine stays endpoint-only this phase; just reserve/label.)

## Validation (must pass; GPU-free)
- New unit tests for: atomic write + Windows-retry path; campaign.json schema; JSONL append +
  torn-line truncation + per-line validation + dedup; bench-level + item-level resume skip logic;
  hard-invariant refusal (exit 40); exit-code taxonomy; status/collect; redaction (no secrets in
  any persisted file).
- **Kill-and-resume integration test against a mock OpenAI-compatible endpoint:** start a run, kill
  the worker mid-bench AND between benches, `--resume`, and assert the assembled
  `localbench-run.json` equals an uninterrupted run (same items, scores, aggregates) and that no
  completed item is re-requested. No GPU, no real model.
- Keep the existing suite green: `cli\.venv\Scripts\python.exe -m pytest cli/tests -q`.
- `git hash-object cli/runs/board/board_v1.json` must remain `3d058e60…` and the manifest
  `f923abb3…` before every commit.

## Explicitly deferred (NOT this build — future to-do items)
- The turnkey launcher `localbench bench` (preflight → pull/verify GGUF → start llama.cpp with
  pinned flags → run engine → resume → submit). **Engine stays endpoint-only; managed-serve lives
  in the launcher and is its default.**
- Wheel hosting / distribution; going public (R2 creds + Pages secrets + flip private→public).
- ETA, web-visible run state, full GPU thermal policy, submission automation, full crypto record
  chain. (The serve-fingerprint + trust-tier *fields* are reserved now; the launcher fills them.)

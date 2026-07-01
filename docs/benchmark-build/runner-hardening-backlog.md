# Runner Hardening Backlog

These items should be addressed before asking external users to run the full
local-bench suite.

## P0 - Required Before Public Runner Use

1. Campaign state file
   - Write `run.status.json` at startup.
   - Update it atomically after every meaningful transition.
   - Include `state`, `current_bench`, `current_item_index`, `current_item_id`,
     `completed_items`, `total_items`, `started_at`, `updated_at`, `exit_code`,
     and `failure_reason`.

2. Per-benchmark checkpoints
   - Write item-level JSONL under `benchmarks/<bench>.items.jsonl`.
   - Write aggregate checkpoints under `benchmarks/<bench>.aggregate.json`.
   - Mark a benchmark complete before moving to the next one.

3. Resume support
   - Add `localbench run --resume <campaign-dir>`.
   - Validate suite hash, model id, lane, tier, reasoning activation, endpoint
     compatibility, and benchmark selection.
   - Skip completed item IDs and preserve original metadata.

4. Failure-state capture
   - On exception or signal, write `run.status.json` with failure details.
   - Include stderr tail, server-log tail, monitor snapshot, and last completed item.

5. Built-in watchdog
   - Detect no item completion for N minutes.
   - Detect expected-active GPU becoming idle.
   - Detect endpoint unreachable.
   - Detect OOM, CUDA errors, prompt rendering failures, and AppWorld harness failures.
   - Exit with a clear failure state instead of silently stalling or disappearing.

## P1 - Strongly Recommended

1. `localbench status <campaign-dir>`
   - Print a concise progress report from `run.status.json`.
   - Include current bench, completed items, elapsed time, estimated progress, and health.

2. `localbench collect <campaign-dir>`
   - Produce a support bundle with command, config, status, logs, monitor tails,
     system info, and partial checkpoints.
   - Redact secrets.

3. Better stdout progress
   - Print one line per benchmark start/end.
   - Print periodic item progress.
   - Keep output parseable for wrappers.

4. Safer supervisor
   - Avoid hardcoded campaign IDs.
   - Accept pilot campaign, pid path, server log, and output paths as arguments.
   - Fail loudly if the configured pilot does not match the live process.

5. Campaign manifest
   - Write `campaign.json` with immutable run inputs:
     model, quant, hardware, GPU UUID, endpoint, suite hash, tier, lane,
     benchmark list, command, git commit, and environment summary.

## P2 - Nice To Have

1. ETA estimation
   - Estimate progress per bench using item count and moving average duration.

2. Web-visible run state
   - Allow a campaign folder to be rendered into a local status page.

3. Hardware run policy
   - Encode "no parallel benchmark runs" and GPU exclusivity checks in the runner.

4. Cleanup policy
   - Track downloaded models and temporary artifacts per campaign.
   - Provide a dry-run cleanup report before deleting anything.

## Acceptance Criteria

Before third-party distribution, an interrupted run should answer all of these
without manual log archaeology:

- Which benchmark was running?
- Which item was last completed?
- What failed?
- Is the run resumable?
- Which files should be sent for support?
- Did the machine meet benchmark health requirements?


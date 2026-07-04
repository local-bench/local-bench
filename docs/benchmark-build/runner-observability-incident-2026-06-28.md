# Runner Observability Incident - 2026-06-28

## Summary

During the Gemma 4 12B QAT RTX 5090 pilot, the benchmark process exited without
writing `localbench-run.json`. The monitor initially treated this as a quiet
state instead of an actionable failure. This created a false impression that a
long benchmark was still progressing.

The core issue was not only the failed run. The suite currently writes the final
run JSON only after all selected HTTP benchmarks and AppWorld complete. If the
process exits mid-run, there are no per-benchmark or per-item checkpoint files
in the campaign folder.

## Runs

Original pilot:

- Campaign: `gemma-4-12b-qat-ud-q4_k_xl-c32768-20260628-103251`
- Output expected: `runs/campaigns/gemma-4-12b-qat-ud-q4_k_xl-c32768-20260628-103251/localbench-run.json`
- Outcome: `localbench-run.json` missing.
- Supervisor behavior: stopped at validation and did not launch the comparator queue.
- Server-log estimate: about 591 completed generation requests.
- Capped-thinking uses two HTTP completion passes per item, so this is about 295 completed items.
- Likely stop point: inside `mmlu_pro`, before `ifbench`, `tc_json_v1`, `lcb`, or `appworld_c`.

Rerun:

- Campaign: `gemma-4-12b-qat-ud-q4_k_xl-c32768-rerun-20260628-170822`
- Started with explicit `localbench` exit-code capture.
- Supervisor repointed to this campaign.
- Status at 2026-06-28 17:32 AEST: still running, GPU active, no result JSON or exit code yet.
- Server-log estimate at that time: about 44 completed generation requests, about 22 completed items.
- Likely current benchmark: still `mmlu_pro`.

Latest snapshot:

- Time: 2026-06-28 17:36 AEST.
- RTX 5090 monitor: healthy, about 14.8 GiB VRAM used, about 86 percent GPU utilization.
- Server-log estimate: 54 launched requests, 53 completed requests, about 26 completed items.
- Server errors: none detected.
- Result JSON: not yet written.
- Exit-code file: not yet written.
- Likely current benchmark: still `mmlu_pro`.

## Monitoring Lessons

The previous heartbeat was too broad. It checked GPU health and Vast availability,
but it did not treat a `localbench` process exit with missing JSON as an urgent
benchmark failure.

The heartbeat has been updated to notify on:

- `localbench` process exit.
- exit-code file appearing.
- result JSON appearing.
- supervisor exit.
- GPU idle while a run is expected active.
- monitor breaches or errors.
- Vast availability changes.

## Vast Constraint

The RTX 6000 Pro Vast host remains watch-only while a renter is active.

Rules:

- Do not run workloads on Vast unless the approved Vast self-rented/instance path is clear.
- Do not touch renter containers.
- Do not restart host services.
- Do not alter listing, pricing, Docker, or Vast host configuration during rental.

## Design Gap

`localbench run` currently behaves like:

1. Resolve suite and selected benches.
2. Run HTTP benches in memory.
3. Run AppWorld if selected.
4. Write one final `localbench-run.json`.

If the process stops before step 4, the campaign folder cannot tell us which
benchmark or item was last completed. This is not acceptable for third-party
benchmark runs.

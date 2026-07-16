# Correction: gemma-4-31b-it-q4km-s2v5 wall time (2026-07-17)

## What changed
Two values in `gemma-4-31b-it-q4km-s2v5.json` `totals`:

| field | before | after |
|---|---|---|
| `totals.wall_time_seconds` | 12580.048545999918 (3.49 h) | **100257.26 (27.85 h)** |
| `totals.completion_tokens_per_second` | 385.436906882349 | **48.36372946956659** (= 4,848,815 / 100,257.26) |

`manifest.execution` is deliberately untouched: its `wall_clock_s` (12,580.05 s) is the final
process's faithful self-report and is internally consistent with that block's
`started_at`/`finished_at` (2026-07-11 19:35:52Z → 23:05:32Z). Nothing in the board or site
pipeline consumes it.

## Why
The source run (`gemma31b-q4km-v2-full`, RTX 5090 reference rig) executed in **three
segments**, and the CLI recomputes totals on every (re)run with `wall_time =
time.perf_counter() - started_perf` of the *current process only*
(`orchestrate.py`), while token totals span every segment. The last writer — the
2026-07-12 agentic re-run — therefore recorded cumulative tokens against its own
3.49 h clock. The record itself carries the evidence: `resumed: true`,
`resume_count: 1`, and `run_started_at/run_finished_at` equal to the final
segment's window.

The corrupted value implied 385.4 completion tok/s from a model whose measured
`perf.decode_tps` is 63.08 — physically impossible (6.1× decode). Derived board
fields `tok_s` and `latency_s_median` inherited the corruption.

## Corrected value: method
Sum of the three segment process durations (the same elapsed-process semantic every
other boarded run's wall time uses):

| segment | window (AEST) | duration | source |
|---|---|---|---|
| 1. full run (crashed near end) | 07-10 15:13:56 → 07-11 13:07:59 | 78,843 s | transcript file create→last-write (`gemma31b-q4km-v2-full.transcript.log`); the in-process clock died unwritten |
| 2. static resume | 07-11 14:26 → 16:54 | 8,834.21 s | CLI-printed `wall 8834.21s` in `gemma31b-q4km-v2-full-resume.transcript.log` |
| 3. agentic re-run (3rd attempt) | 07-12 05:35 → 09:05 | 12,580.05 s | recorded by the process itself (the value that had overwritten totals) |

**Total: 100,257.26 s = 27.85 h.**

Cross-checks (all cohere):
- Physics floor: 4,848,815 completion tokens / 63.08 tok/s + 5,527,046 prompt tokens /
  2,425 tok/s ≈ 79,146 s of pure generation ≤ total. Implied/decode ratio after
  correction: 0.767 — in line with the other four ranked runs (0.84–0.93).
- Item-record floor: per-item `started_at`+latency spans in
  `benchmarks/*.raw_results.jsonl` cover 75,198 s of segment 1 alone (the resume
  segment's 96 items carry no llama.cpp timings — `timings_coverage` 0.934 — and the
  agentic phase has no per-item records, which is why the item-level route cannot
  reconstruct the total and process spans are used).
- Onramp estimator for a 31B on this rig: ~26 h midpoint.

Segment 1's figure is a process-boundary measurement (±seconds of wrapper overhead)
rather than an in-process `perf_counter`; the uncertainty is minutes against a 27.85 h
total.

## Guard added with this correction
`board_scoring._validate_wall_time_consistency` now fails the board build when
`completion_tokens / wall_time_seconds > 1.25 × perf.decode_tps`, so a
last-segment-only wall time can never board again. The upstream CLI fix (persist
per-segment wall and accumulate on resume) is tracked for 0.4.x.

# Benchmark Data Completion Backlog - 2026-06-28

Scope: fill missing benchmark data for the website while keeping benchmark-suite
engineering separate.

Do not rerun already measured Knowledge/Instruction/Tool-calling rows unless a
row is missing provenance, has a quarantined axis, or needs a direct matched
comparison for a new quant/runtime.

## Current Coverage Snapshot

Source checked:

- `web/public/data/runs/*.json`
- `web/public/data/index.json`
- `web/public/data/agentic.json`
- `web/data_sources.json`
- `cli/runs/agentic/*.scored.run*.json`

Published run rows:

| Axis | Published run rows |
| --- | ---: |
| Knowledge | 23 |
| Instruction | 23 |
| Tool-calling | 17 |
| Coding | 0 |
| Agentic | 0 in ranked run axes |

Separate experimental agentic display currently exposes only:

| Model | Agentic ASR | Notes |
| --- | ---: | --- |
| Gemma 4 31B Q4_K_M | 11.46% | 96-task AppWorld-C receipt exists |
| Qwen3.6 27B Q6_K | 14.58% | 2 scored 96-task AppWorld-C receipts exist |

Raw valid AppWorld-C scored receipts also exist for more Qwen3.6 27B variants,
but they are not fully represented in the ranked run axes.

## Do Not Spend Time On First

These already have enough K/I data for current site use:

- Gemma 4 12B IT ladder: BF16, Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K.
- Gemma 4 12B Coder Fable5 Q8_0.
- Ornith 1.0 35B: BF16, Q8_0, Q6_K, Q5_K_M.
- Qwen3.6 35B A3B: Q8_0, Q6_K, Q4_K_M.
- Qwen3 Coder Next: Q8_0, Q6_K.
- Qwen3.6 27B ladder: Q8_0, Q6_K, Q4_K_M, Q3_K_M, Q2_K for K/I.
- Gemma 4 31B Q4_K_M for K/I.

## Priority 1 - Promote/Integrate Existing Agentic Receipts

Before running new agentic jobs, use the valid scored receipts already on disk:

| Family | Quant/runtime | Existing receipts |
| --- | --- | --- |
| Qwen3.6 27B | Q8_0 | `cli/runs/agentic/qwen36-27b-Q8_0.scored.run1.json` |
| Qwen3.6 27B | Q6_K | `cli/runs/agentic/qwen36-27b-Q6_K.scored.run1.json`, `run2` |
| Qwen3.6 27B | Q4_K_M | `cli/runs/agentic/qwen36-27b-Q4_K_M.scored.run1.json` |
| Qwen3.6 27B | Q3_K_M | `cli/runs/agentic/qwen36-27b-Q3_K_M.scored.run1.json`, `run2` |
| Qwen3.6 27B | Q2_K | `cli/runs/agentic/qwen36-27b-Q2_K.scored.run1.json` |
| Qwen3.6 27B distill | Qwopus Q4_K_M | `cli/runs/agentic/qwopus36-27b-Q4_K_M.scored.run1.json` |
| Qwen3.6 27B coder distill | Qwable NVFP4 | `cli/runs/agentic/qwable-5-27b-coder.scored.run1.json`, `run2` |
| Gemma 4 31B IT | Q4_K_M | `cli/runs/agentic/gemma4-31b-Q4_K_M.scored.run1.json` |

Action:

1. Decide whether these receipts are valid under the current AppWorld-C identity
   after the BI-1 watchdog fix.
2. If valid, wire them into the website/model detail data before scheduling new
   AppWorld-C runs.
3. Where two runs exist, publish the mean and run-to-run spread.
4. Keep Qwopus/Qwable marked `agentic-only` until full K/I/tool/coding rows exist.

## Priority 2 - Agentic-Only Backfill Runs

Run AppWorld-C only, serially, after the active local run is resolved or stopped.

Local RTX 5090 candidates:

| Model/quant | Why |
| --- | --- |
| Gemma 4 12B IT Q4_K_M | Existing AppWorld-C was quarantined; needed for matched Gemma 12B ladder |
| Gemma 4 12B IT Q6_K | Best current Gemma 12B site row; likely representative ladder point |
| Gemma 4 12B IT Q8_0 | Near-lossless point for quant-loss comparison |
| Gemma 4 12B IT Q2_K | Low-end quant-loss point |
| Gemma 4 12B Coder Fable5 Q8_0 | Distill/tuning delta against Gemma 12B |
| Gemma 4 12B QAT UD-Q4_K_XL | Current live run may fill this if it completes cleanly |

Vast RTX 6000 Pro candidates, only via approved self-rented instance path:

| Model/quant | Why |
| --- | --- |
| Qwen3.6 35B A3B Q4_K_M | Existing AppWorld-C quarantined; main 35B MoE ship point |
| Qwen3.6 35B A3B Q6_K | Higher-quality comparison |
| Qwen3.6 35B A3B Q8_0 | Near-lossless comparison |
| Qwen3 Coder Next Q6_K | Coder-specialist comparison |
| Qwen3 Coder Next Q8_0 | Near-lossless coder-specialist comparison |
| Ornith 1.0 35B Q6_K | Current best Ornith non-agentic row |
| Ornith 1.0 35B Q8_0 | Near-lossless Ornith point |

Do not start any Vast run while the host has an active renter unless Vast assigns
our own isolated 1x GPU instance/container through the approved path. Do not run
directly on the host or touch renter containers/services.

## Priority 3 - Tool-Calling Gaps

Tool-calling is missing for 6 published rows:

- Qwen3.6 27B Q8_0.
- Qwen3.6 27B Q6_K.
- Qwen3.6 27B Q4_K_M.
- Qwen3.6 27B Q3_K_M.
- Qwen3.6 27B Q2_K.
- Gemma 4 31B Q4_K_M.

These are much cheaper than full K/I reruns. Run `tc_json_v1` only if the runner
supports bench selection cleanly; otherwise defer until the data harness is
separated enough to avoid rerunning K/I.

## Priority 4 - Coding Axis

Coding has zero published rows. Do not treat the site as complete until coding is
either populated or explicitly marked pending.

Initial coding candidates:

- Gemma 4 12B IT Q6_K, Q4_K_M, Q8_0.
- Gemma 4 12B Coder Fable5 Q8_0.
- Qwen3.6 27B Q6_K, Q4_K_M.
- Qwen3.6 35B A3B Q4_K_M.
- Qwen3 Coder Next Q8_0 and Q6_K.
- Gemma 4 31B Q4_K_M.

Run coding serially on one GPU at a time. Publish runtime/token metrics separately
from capability.

## Active Run Note

Current live local run:

`gemma-4-12b-qat-ud-q4_k_xl-c32768-rerun-20260628-170822`

This run may produce a useful QAT UD-Q4_K_XL row, but it is not the fastest way
to complete the existing website gaps because most K/I/tool data for Gemma 4
12B is already known. Do not stop it without explicit approval, but future runs
should prefer missing-axis backfills over full `--bench all` campaigns.

## Operating Rules

- One benchmark workload per GPU at a time.
- Backfill a missing axis; do not run a full campaign merely to update one axis.
- Preserve raw receipts and diagnostics before cleanup.
- Delete downloaded model weights after artifact verification unless explicitly
  retained for a near-term matched comparison.
- Vast artifacts must be copied home before any remote cleanup.
- Mark quarantined AppWorld-C data as invalid until diagnostics prove it is a
  model result, not a harness/client-path artifact.

## Execution Plan After Aborting Full 5090 Run

The long Gemma QAT full run was intentionally aborted on 2026-06-28 because it
was re-running mostly known K/I/tool data and was not the fastest route to
closing website gaps.

Abort marker:

`runs/campaigns/gemma-4-12b-qat-ud-q4_k_xl-c32768-rerun-20260628-170822/ABORTED-BY-USER.txt`

### Phase 0 - No-GPU Data Promotion

Start here before spending GPU time.

1. Re-read existing `cli/runs/agentic/*.scored.run*.json` receipts.
2. Confirm they are valid under the current AppWorld-C identity and not affected
   by the pre-BI-1 hang/diagnostic issue.
3. Regenerate `web/public/data/agentic.json` and model detail data so every
   existing valid Qwen3.6 27B, Qwopus, Qwable, and Gemma 31B receipt is visible.
4. Do not create new benchmark output in this phase.

### Phase 1 - RTX 5090 Agentic Backfill

Use targeted AppWorld-C only:

`localbench run --bench appworld_c ...`

Run serially. Suggested order:

1. Gemma 4 12B IT Q6_K - best current Gemma 12B site row.
2. Gemma 4 12B IT Q4_K_M or QAT UD-Q4_K_XL - practical mid-quant point.
3. Gemma 4 12B IT Q8_0 - near-lossless reference.
4. Gemma 4 12B IT Q2_K - low-end quant-loss point.
5. Gemma 4 12B Coder Fable5 Q8_0 - tuning/distill delta.

Stop after each run, verify artifacts, and clean model files unless the next
run uses the same model.

### Phase 2 - Cheap Tool-Calling Backfill

Use targeted tool-calling only:

`localbench run --bench tc_json_v1 ...`

Priority rows:

1. Qwen3.6 27B Q6_K.
2. Qwen3.6 27B Q4_K_M.
3. Qwen3.6 27B Q8_0.
4. Qwen3.6 27B Q3_K_M.
5. Qwen3.6 27B Q2_K.
6. Gemma 4 31B Q4_K_M.

These should be cheaper than AppWorld-C and can be used to close the current
17/23 tool-calling coverage gap.

### Phase 3 - Coding Axis Seed

Use targeted coding only:

`localbench run --bench lcb ...`

Initial coding seed set:

1. Qwen3 Coder Next Q8_0.
2. Qwen3 Coder Next Q6_K.
3. Gemma 4 12B Coder Fable5 Q8_0.
4. Qwen3.6 27B Q6_K.
5. Qwen3.6 27B Q4_K_M.
6. Gemma 4 12B IT Q6_K.
7. Gemma 4 12B IT Q4_K_M.
8. Gemma 4 31B Q4_K_M.

This gives the site an initial coding signal across coder-specialist, general,
and quant-comparison rows.

### Phase 4 - Vast-Only Backfill

Do not start while the host has an active renter unless the approved Vast
self-rented/instance path assigns an isolated 1x GPU benchmark container.

First Vast backfills once approved:

1. Qwen3.6 35B A3B Q4_K_M AppWorld-C.
2. Qwen3 Coder Next Q8_0 AppWorld-C.
3. Qwen3 Coder Next Q6_K AppWorld-C.
4. Ornith 1.0 35B Q6_K AppWorld-C.
5. Coding for Qwen3 Coder Next and Qwen3.6 35B A3B if not already covered.

## Live Execution Notes - 2026-06-28

Active 5090 backfill:

- Campaign: `runs/campaigns/gemma-4-12b-it-q6_k-lcb-retry-20260628-190521/`
- Bench: `lcb`
- Model server: Gemma 4 12B IT `Q6_K`, RTX 5090, 32k context, concurrency 1.
- Status at launch verification: active localbench process, active llama-server,
  RTX 5090 decoding at about 87-88% utilization.
- Monitor automation: `watch-5090-q6-lcb-backfill`.

Non-publishable attempts created during setup:

- `runs/campaigns/gemma-4-12b-it-q6_k-appworld-c-20260628-190251/`
  exited immediately because the current Windows runner cannot provide the
  AppWorld sandbox: `appworld` was not importable, `APPWORLD_ROOT` was unset,
  and `bwrap` was unavailable. This is an AppWorld runner-environment gap, not
  a model score.
- `runs/campaigns/gemma-4-12b-it-q6_k-lcb-20260628-190429/` exited immediately
  because the 12B GGUF repo tokenizer was not present in the offline HF cache.
  The retry uses the previously known-good cached Gemma 4 prompt-renderer id
  `unsloth/gemma-4-31B-it`.

Immediate follow-up:

1. Let the active `lcb` run finish before starting any other 5090 benchmark.
2. Treat AppWorld-C as blocked until a Linux/WSL runner has AppWorld, `bwrap`,
   and `APPWORLD_ROOT` configured.
3. After the `lcb` result lands, decide whether to continue the Gemma 12B coding
   ladder or switch to cheaper `tc_json_v1` gaps.

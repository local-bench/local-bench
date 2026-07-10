# AppWorld-C funnel harness — frozen subsets + the exact GPU-run commands

Date: 2026-06-24. Status: **HARNESS BUILT + MOCK-TESTED GPU-FREE.** This is the staged-campaign
orchestration the (separate, explicitly-gated) GPU run drives on top of the already-built + verified
Protocol C loop (`appworld-protocol-c-loop-results.md`). It adds the `ChatCompletionsClient`
(`ModelClient` over an OpenAI-compatible endpoint) and the funnel campaign logic: frozen
pre-registered task subsets, run + persist, the LOCKED 2-rerun repeatability rule, and the early-stop
check.

GPU-free / model-free: everything here is proven with a MOCK transport + a scripted/mock model
client + an in-memory `FakeSandbox` (61 host-agnostic units pass on Windows Py3.14). NO model is
loaded, NO `llama-server` is started, port 8000 stays idle. The agentic axis stays
**unregistered / weight-0** — nothing here touches the scorer / board / registry. The actual GPU
funnel is the gated follow-up (commands at the bottom).

---

## WHAT WAS BUILT (all additive)

| File | Role |
|---|---|
| `cli/src/localbench/scoring/agentic_exec/chat_client.py` | **`ChatCompletionsClient`** — a `ModelClient` over an OpenAI-compatible `/v1/chat/completions` endpoint. **Stdlib only** (`urllib` + `json`; no httpx/openai SDK → import-safe on every host). `complete(messages, params)` POSTs `{model, messages, temperature, top_p, seed, max_tokens, stream:false}` and returns `ModelResponse(text=choices[0].message.content, finish_reason=choices[0].finish_reason, output_tokens=usage.completion_tokens)`. **Graceful degradation contract (documented):** timeout / non-200 / malformed-or-missing fields NEVER raise — they return an empty-text `ModelResponse(text="", finish_reason="error")`, which the loop already treats as a recoverable **format failure** (corrective observation injected) so one blip costs one turn, not the task. Elevated `format_failure_rate` then makes any endpoint flakiness visible. |
| `cli/src/localbench/scoring/agentic_exec/funnel.py` | **The funnel campaign harness.** Frozen subset selection (`select_subset` / `subset_for_stage` / `SubsetSpec` with a `manifest_hash`); run + persist a stage (`run_stage` → results JSON); the LOCKED reruns + run-to-run abs-delta (`run_with_reruns` / `RerunAggregate`); the early-stop check (`evaluate_early_stop` / `EarlyStopSignal`). Imports NO model SDK and NO sandbox — both arrive via the benchmark's factory seam. |
| `cli/tools/appworld_c_funnel.py` | **The GPU-run CLI runner.** Loads real AppWorld ids (`appworld.load_task_ids`) + per-task metadata, builds the frozen subset, points the client at the llama-server, runs the stage with reruns + early-stop. GPU-free modes: `--print-subset` (freeze/verify a manifest, no server) and `--dry-run` (print the plan, no model calls). |
| `cli/tests/test_appworld_c_funnel_units.py` | **31 GPU-free units.** Client request shape (MOCK transport) + parsing + every error path; subset determinism / freeze-hash / stratification / seed-sensitivity; run+persist (JSON shape on disk); the 2-rerun rule + the 3rd-run-on->5pp-drift trigger; all early-stop conditions; aggregation. NO model, NO server, NO bwrap. |

The GPU run swaps NOTHING in the loop/sandbox — it just builds a `ChatCompletionsClient` as the
`model_factory` (via `funnel.chat_client_factory`) and reuses `appworld_sandbox_factory()`.

---

## FROZEN, PRE-REGISTERED TASK SUBSETS

The selection is **deterministic, seeded, stratified, and computed on SPLIT MEMBERSHIP ONLY — never
on any model's results.** It is therefore reproducible and demonstrably **not tuned**. The split
sizes are AppWorld's documented + locally-verified sizes (`appworld-install-results.md`): train 90 /
**dev 57** / **test_normal 168** / test_challenge 417.

### Calibration vs scoring split assignment (the key anti-overfit decision)

| Stage | Split | Size | Why this split |
|---|---|---|---|
| **smoke** | `dev` | **1** (or `--wide-smoke` → 6) | Find loop bugs on 1 system; no score. Dev is the calibration pool the loop budgets (turn cap 24) were tuned on, so smoke/lite legitimately live here. |
| **lite** | `dev` | **36** | Non-saturation + failure-taxonomy on 2 contrasting systems. Still dev (calibration). |
| **scored** | `test_normal` | **96** | The displayed candidate number. Drawn from AppWorld's standard **held-out** evaluation split — strictly separate from the dev pool the loop was calibrated on. (dev=57 < 96, so the scored set cannot be dev anyway; test_normal=168 is the natural, untuned source.) |

This keeps the LOCKED rule honest: *"calibrated on dev ONLY; never tune on test splits."* The scored
column is measured on tasks the harness budgets never saw.

### Exact selection algorithm (`funnel.select_subset`, `selection_version="v1"`)

Pre-registration seed: **`SELECTION_SEED = 20260624`** (fixed forever for the v1 manifest).

1. **Canonical start order** — drop duplicates; sort the split's task ids lexicographically (so the
   result does not depend on how `load_task_ids` happened to order them).
2. **Stratify** into buckets keyed by `(difficulty, primary_app)`, read from each task's
   `$APPWORLD_ROOT/data/tasks/<id>/ground_truth/metadata.json` (difficulty band + the app). Tasks
   whose metadata can't be read fall into a single sentinel bucket (selection still works).
3. **Order within each stratum** by `sha256("{seed}:{task_id}")` — a fixed hash (NOT Python's salted
   `hash()`), so the order is reproducible across processes/interpreters and is decoupled from id
   lexical order (the sample is not biased toward low/high ids).
4. **Round-robin** across strata (strata visited in sorted-key order), taking one task at a time
   until `size` are collected → a stratified, representative sample.
5. If `size` exceeds the pool, take the whole pool.

The resulting `SubsetSpec.manifest_hash` is `sha256` over
`{split, size, seed, selection_version, ordered task_ids}`. **Two independent runs of the selection on
the same split membership produce the same ids in the same order and the same hash** — this is the
freeze check (proven in the units; the mock runner reproduced the 96-task hash byte-identically on
repeat calls).

### Freezing the manifest (do this once, GPU-free, before any scored GPU run)

Run inside the WSL appworld venv (it needs `load_task_ids` + metadata; no GPU, no server):

```bash
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=<appworld-root> PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && <wsl-python> cli/tools/appworld_c_funnel.py --stage scored --print-subset'
```

This prints the 96 task ids (in run order) + the `manifest_hash`. Record that hash in the
AppWorld-C manifest / `launch_freeze_v1.json`; after freezing, the runner will reproduce the same
hash and any drift (a different AppWorld data version, a changed seed) is caught immediately. Repeat
for `--stage smoke` and `--stage lite` to freeze those too.

---

## RERUNS + RUN-TO-RUN DELTA (the LOCKED repeatability rule)

Per the launch plan, a **displayed row gets 2 full reruns**; if the max abs run-to-run delta on the
headline metric (ASR) **exceeds 5pp**, do a **3rd** run and report the **mean**. `funnel.run_with_reruns`
implements exactly this:

- runs the row `base_count` times (LOCKED default **2**), each persisted as `…run1.json`, `…run2.json`;
- computes `max_abs_delta_pp` = (max − min) of the per-run ASR series × 100;
- if that exceeds `DELTA_TRIGGER_PP = 5.0`, runs a 3rd (`…run3.json`) and recomputes over all three;
- returns a `RerunAggregate` with the ASR series, the max abs delta (pp), `triggered_third_run`, and
  the mean ASR — JSON-serialisable.

Because **1 task on a 96-set ≈ 1.04pp**, the GPU run shows **bootstrap CIs** beside every ASR and
does not make fine-grained rank claims on small deltas (the loop/aggregate already expose the
per-task rows a task-clustered bootstrap needs).

---

## EARLY-STOP CHECK (the LOCKED stop conditions)

`funnel.evaluate_early_stop(report, cross_model_asr=…)` flags, with human-readable reasons:

| Condition | Fires when | Meaning |
|---|---|---|
| `near_zero` | ASR ≤ 2% (~≤2/96) | The model can't do the task; nothing to rank. |
| `near_perfect` | ASR ≥ 98% (~≥94/96) | Saturated; no discrimination, the column adds no signal. |
| `harness_dominated` | ≥ 80% of **non-success** tasks ended in `cap_exceeded` / `no_final_answer` / `harness_error`, or carried any parser/syntax/runtime error | **Construct-validity red flag** (the oracle's central risk): the column is measuring Protocol C harness friction, not interactive API-coding skill. |
| `within_noise` | (optional) cross-model ASR spread < 3pp | Ranks across models aren't meaningful; stop fine comparison. |

It returns `should_stop` + the reasons + the `harness_failure_share`. (The two remaining launch-plan
stop signals — *"order just mirrors IFBench + code-proxy"* and *"any canary regression"* — need
cross-axis correlation + the canary suite and are computed by the caller, not from a single report.)

---

## EXACT PER-STAGE GPU-RUN COMMANDS (the gated follow-up)

**Prerequisites for the live run (all gated on explicit GPU go-ahead):**
- The 5090 free + an explicit go-ahead (standing rule: never launch GPU work unprompted).
- A built `llama-server` (llama.cpp) + the GGUF weights for the model under test.
- The frozen manifest hashes recorded (see "Freezing the manifest" above).

### Step A — start the model server (ONLY when gated; this is the GPU step)

On the box, serve the model on **`http://127.0.0.1:8000`** (OpenAI-compatible). Example with
llama.cpp; greedy decoding is enforced per-turn by the client (`temperature=0, seed=0`), so server
sampler defaults don't matter:

```bash
# (gated GPU step — do NOT run during the GPU-free build)
llama-server -m /path/to/<model>.gguf --host 127.0.0.1 --port 8000 -c 8192 -ngl 999
# confirm it's up:
curl -s http://127.0.0.1:8000/v1/models
```

The `--model` you pass the runner must be the id the server reports at `/v1/models`.

### Step B — point the funnel at it and run each stage

All commands run inside the WSL appworld venv (for `load_task_ids` + the bwrap sandbox), with the
determinism env, exactly like the scripted loop proof:

```bash
# common WSL prefix (reused below):
WSLPRE='cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=<appworld-root> PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && <wsl-python> cli/tools/appworld_c_funnel.py'
```

**3.1 smoke** (1 system, find loop bugs, no score — 1 task, or `--wide-smoke` for 6):
```bash
wsl bash -lc "$WSLPRE --stage smoke --base-url http://127.0.0.1:8000 \
  --model <served-id> --label <model-label> --reruns 1"
```

**3.2 lite** (~36 dev tasks; run for **2 contrasting systems** to check non-saturation + the failure
taxonomy — swap `--model`/`--label` for the second):
```bash
wsl bash -lc "$WSLPRE --stage lite --base-url http://127.0.0.1:8000 \
  --model <served-id> --label <model-label>"
```

**3.3 FREEZE** the AppWorld-C manifest now (prompt, cap 24, timeouts, **the 96 task IDs/order**,
scorer, diagnostics schema) — record the `--print-subset` hash. After this, **no prompt/cap tuning on
scored tasks**; if an invalidating harness bug is fixed, DISCARD + rerun affected scored runs.

**3.4 first 96-task pass** across the Qwen ladder + gemma (each is a `--model`/`--label`; the 2-rerun
rule below gives the displayed row). Check the early-stop reasons the runner prints after each:
```bash
wsl bash -lc "$WSLPRE --stage scored --base-url http://127.0.0.1:8000 \
  --model <served-id> --label <model-label>"
```

**3.5 displayed rows = the 96-task pass with the LOCKED 2 reruns** (the runner does this by default:
`--reruns 2`, auto-adding a 3rd + mean iff ASR drift > 5pp). One invocation per displayed model
yields `…scored.run1/2[/3].json` under `cli/runs/agentic/` + the rerun aggregate + early-stop verdict:
```bash
wsl bash -lc "$WSLPRE --stage scored --base-url http://127.0.0.1:8000 \
  --model <served-id> --label <model-label>"   # --reruns defaults to 2
```

### Where results land

Persisted under **`cli/runs/agentic/`** (git-ignored: `.gitignore` covers `runs/`) as
`<label>.<stage>.run<k>.json`. Each file is self-describing: model label/endpoint, the loop config,
the frozen subset (ids + `manifest_hash`), a UTC timestamp, and the full `BenchmarkReport` (ASR +
every diagnostic rate + per-task rows). For the GPU-free mock test the units write to a `tmp_path`
instead — `cli/runs/` is only written when actually run.

---

## RE-RUN THE GPU-FREE PROOF (independent verification, no GPU/model/server)

```bash
# 31 funnel + chat-client units (Windows Py3.14 OR WSL; MOCK transport, no endpoint):
%LOCALAPPDATA%\Programs\Python\Python314\python.exe -m pytest cli\tests\test_appworld_c_funnel_units.py -q
#   (expect 31 passed)

# freeze/verify the 96-task manifest with NO GPU (WSL, needs appworld for ids):
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=<appworld-root> PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && <wsl-python> cli/tools/appworld_c_funnel.py --stage scored --print-subset'
#   (prints the 96 ids + manifest_hash; re-run → identical hash)
```

---

## SCOPE NOTE — what this is NOT
The funnel orchestration + client + frozen subsets + the GPU-free proof ONLY. NOT done here
(deliberately): loading any model / starting `llama-server` / any scored GPU run; registering the
agentic axis (stays weight-0 candidate, zero headline impact); the submission-verifier / site work.
The `ModelClient` seam stays clean: the GPU run is just "start the server, point the client at it,
run the stage."

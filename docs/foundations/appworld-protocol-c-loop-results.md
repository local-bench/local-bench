# AppWorld-C Protocol C agent LOOP — BUILD RESULTS

Date: 2026-06-24. Status: **LOOP WORKS END-TO-END VIA THE SCRIPTED AGENT.** Builds the
Protocol C agent loop on top of the already-built + security-verified `AppWorldSandbox`
(see `appworld-sandbox-build-results.md`), turning the sandbox into a runnable benchmark.

GPU-free / model-free: the only "agent" exercised here is a deterministic hand-written
`ScriptedSolverAgent` (NO LLM, NO `llama-server`, port 8000 untouched, GPU idle). The
real-model GPU benchmark is a SEPARATE follow-up that swaps the scripted agent for an
OpenAI-compatible chat client at the `ModelClient` seam — it is NOT run here.

Additive only: new modules under `cli/src/localbench/scoring/agentic_exec/` + a tool + tests.
No `web/`, no `axes.py`/scorecard/scorer/registry wiring, no `top_k`/lane changes, no
`cli/runs/` changes. The agentic axis stays **unregistered (weight-0 candidate)**. No
`git commit`/`push`.

---

## HEADLINE — does the loop work? (re-run yourself with the commands below)

| Check | Requirement | Result |
|---|---|---|
| **Scripted agent solves dev tasks THROUGH the loop on the REAL sandbox** | ≥2 → `success: True` | **2/2 success: True** (`fac291d_1`, `50e1ac9_1`), ASR **1.000** ✅ |
| **Diagnostics recorded correctly** | per-task block/turn/error/api counts populated | ✅ (sample below) |
| **Failure path — format failure → corrective observation → recover** | format failures counted, model recovers | **2 corrective obs → success: True** ✅ |
| **Failure path — cap_exceeded** | hitting turn cap → `outcome=cap_exceeded` | **✅ (max_turns=4 → cap_exceeded)** |
| **Host-agnostic loop units (no bwrap/appworld)** | all green on Windows Py3.14 + WSL Py3.12 | **26/26 PASS both** ✅ |

### Real-sandbox run (the actual GPU-benchmark path, minus the model)

```
PROTOCOL C LOOP — SCRIPTED (NON-LLM) AGENT THROUGH THE REAL SANDBOX
tasks         : ['fac291d_1', '50e1ac9_1']
loop config   : max_turns=24  max_output_tokens_per_turn=1024  max_observation_chars=8000

--- fac291d_1 ---  success=True  outcome=success  collateral=False
    turns_used=3  blocks_run=3  total_api_calls=7   api_docs_uses=0
    format_failures=0  syntax_errors=0  runtime_errors=0  obs_truncations=0  cap_exceeded=False
--- 50e1ac9_1 ---  success=True  outcome=success  collateral=False
    turns_used=3  blocks_run=3  total_api_calls=10  api_docs_uses=0
    format_failures=0  syntax_errors=0  runtime_errors=0  obs_truncations=0  cap_exceeded=False

AGGREGATE
  ASR (agentic_success_rate)   : 1.000 (2/2)
  collateral_damage_rate       : 0.000
  cap_exceeded_rate            : 0.000
  format_failure_rate (/turn)  : 0.000
  syntax_error_rate (/block)   : 0.000
  runtime_error_rate (/block)  : 0.000
  obs_truncation_rate (/block) : 0.000
  api_docs_usage_rate (/task)  : 0.000
  mean_turns_used 3.00  mean_blocks_run 3.00  mean_api_calls 8.50  mean_output_tokens 361.0
  outcome_counts: {'success': 2, 'failure': 0, 'cap_exceeded': 0, 'no_final_answer': 0, 'harness_error': 0}
```

Both answers are derived by the scripted agent *through the loop and the API proxy* — auth
(`supervisor.show_account_passwords` → `spotify.login`), full pagination across the three
libraries, per-song genre/play-count lookups, sort + top-k, with genre/`top_k` parsed from the
task **instruction** (the loop fetched it via the bootstrap) — never from the on-disk gold (the
jail cannot read it). The harness owns finalize: it reads the model's `answer` variable back and
calls `sandbox.finalize`; the model never calls `complete_task`.

### Diagnostics sample (one task, JSON — the GPU run persists exactly this shape)

```json
{
  "task_id": "fac291d_1", "success": true, "outcome": "success", "collateral_damage": false,
  "diagnostics": {
    "turns_used": 3, "blocks_run": 3,
    "format_failures": 0, "syntax_errors": 0, "runtime_errors": 0,
    "cap_exceeded": false,
    "total_api_calls": 7, "api_docs_uses": 0,
    "observation_truncations": 0, "total_output_tokens": 273,
    "finalize_error": null
  }
}
```
Per-turn records (also captured under `diagnostics.turns`):
```
{"index": 1, "had_block": true, "api_calls": 4, "syntax_error": false, "runtime_error": false, "is_final": false, "output_tokens": 93}
{"index": 2, "had_block": true, "api_calls": 1, "syntax_error": false, "runtime_error": false, "is_final": false, "output_tokens": 62}
{"index": 3, "had_block": true, "api_calls": 2, "syntax_error": false, "runtime_error": false, "is_final": true,  "output_tokens": 118}
```

### Failure paths (proven through the REAL sandbox, not just the mock)

```
FAILURE PATH 1: format failure (no_block) ×2 -> corrective observation -> recover
  success=True outcome=success format_failures=2 blocks_run=3 turns_used=5
  turn formats: ['no_block', 'no_block', None, None, None]   -> recovered to success: True

FAILURE PATH 2: cap_exceeded (never finalize), max_turns=4
  success=False outcome=cap_exceeded cap_exceeded=True turns_used=4 blocks_run=4
```

---

## WHAT WAS BUILT (all additive, under `cli/src/localbench/scoring/agentic_exec/`)

| File | Role |
|---|---|
| `model_client.py` | **The model-interface seam.** `ModelClient` Protocol (`complete(messages, params) -> ModelResponse`), `GenerationParams` (temp 0 / seed / per-turn token cap), `ModelResponse(text, finish_reason, output_tokens)`. The ONLY thing the loop needs from a model — scripted agent and a real chat client both implement it. No SDK, no HTTP, import-safe everywhere. |
| `block_parser.py` | Parse one Protocol C turn: extract EXACTLY ONE fenced ```python block; 0/>1/empty → `BlockFormatError` with a corrective message. Detect the `FINAL_ANSWER` sentinel (standalone line or `# FINAL_ANSWER`). Pure. |
| `block_introspect.py` | Static AST count of `apis.<app>.<api>(...)` and `apis.api_docs.*` per block (diagnostics; no exec on the trusted side), plus the deterministic observation-truncation helper. Pure. |
| `prompt.py` | Build the Protocol C system prompt: one-code-block-per-turn rules, auth guidance, **on-demand** `apis.api_docs.*` discovery (does NOT dump ~457 APIs), the harness-owned finalize mechanism (bind `answer` + emit `FINAL_ANSWER`), and the injected task instruction + supervisor email. Renders observations. Pure. |
| `loop_config.py` | `LoopConfig` — LOCKED budgets: **turn cap 24**, per-turn output-token cap (1024), observation char cap (8000), greedy decoding + fixed seed. |
| `loop_types.py` | `TaskOutcome` (success/failure/cap_exceeded/no_final_answer/harness_error), `TurnRecord`, `TaskDiagnostics`, `TaskRunResult`, `BenchmarkReport` — all JSON-serialisable via `as_dict()`. |
| `protocol_c_loop.py` | **The loop.** `run_task(sandbox, model, task_id, config) -> TaskRunResult`. Depends on the sandbox only via a tiny `SandboxLike` Protocol (`run_block`/`finalize`) so it is unit-testable with a mock. |
| `scripted_agent.py` | Deterministic `ModelClient`s: `ScriptedSolverAgent` (solves `fac291d_1`/`50e1ac9_1`), `BadFormatAgent` (no-block / two-block, optional recovery), `NeverFinalizeAgent` (cap test). NO LLM. |
| `benchmark.py` | **The clean entry point** `run_appworld_c_benchmark(...)` + `aggregate(...)` + `appworld_sandbox_factory(...)`. What the GPU benchmark calls. Imports no model SDK / no bwrap. |

| Tool / test | Role |
|---|---|
| `cli/tools/appworld_protocol_c_scripted.py` | Run the loop + scripted agent through the REAL sandbox; print per-task diagnostics + aggregate. Exit 0 iff ≥2 success. |
| `cli/tests/test_appworld_protocol_c_units.py` | 26 host-agnostic units (parser, introspect, prompt, loop via `FakeSandbox` incl. every failure path, scripted agent, aggregate). No bwrap/appworld/model. |
| `cli/tests/test_appworld_protocol_c_acceptance.py` | WSL gate: scripted agent solves ≥2 dev tasks through the loop on the REAL sandbox, with diagnostics asserted. Skips cleanly off-WSL. |

The older stub-based Protocol A modules (`parser.py`/`protocol.py`/`runner.py`/`score.py`/
`adapter.py`/`observations.py`, the one-JSON-object-per-turn design the feasibility proof ruled
NO-GO) are **untouched**; Protocol C is a parallel, additive build with no name collisions.

---

## THE LOOP (as built)

```
build prompt = system(task instruction + supervisor email + format rules + on-demand api_docs)
                (instruction/email fetched on the TRUSTED side via a harness bootstrap block:
                 apis.supervisor.show_active_task() — NOT counted as a model turn or api-call)
repeat up to max_turns (LOCKED = 24):
    resp = model.complete(history, GenerationParams(temp=0, seed=0, max_output_tokens=1024))
    if resp.finish_reason == "length":  format failure (truncated) -> corrective obs ; continue
    action = parse_turn(resp.text)                       # EXACTLY ONE ```python block
    if BlockFormatError (0/>1/empty):   format failure   -> corrective obs ; continue
    count apis.* / api_docs.* in the block (AST, diagnostics)
    obs = sandbox.run_block(action.code)                 # runs in the bwrap jail
    classify obs.error -> syntax_error (SyntaxError…) vs runtime_error
    feed back OBSERVATION(stdout[:8000] + any error) as the next user turn
    if action.is_final (FINAL_ANSWER sentinel):
        answer = read-back `answer` var via a harness block (json-dumped)
        if unusable -> format failure (final_no_answer) -> nudge ; continue
        verdict = sandbox.finalize(answer)               # harness-owned complete_task + evaluate
        outcome = success/failure ; stop
else (no break): outcome = cap_exceeded
record TaskDiagnostics (turn/block counts, format/syntax/runtime failures, cap_exceeded,
                        collateral_damage, total api-calls, api_docs uses, obs truncations,
                        output tokens) + per-turn TurnRecords
```

**Determinism:** greedy decoding + fixed seed handed to the client each turn (LOCKED); AppWorld
fixes task time on the trusted side; observation truncation is deterministic; the loop adds no
randomness. The candidate stays weight-0 / unregistered.

**Diagnostics captured per task** (the axis-falsification set from the LOCKED design):
`turns_used`, `blocks_run`, `format_failures` (+ rate/turn), `syntax_errors` (+ rate/block),
`runtime_errors` (+ rate/block), `cap_exceeded` (+ rate/task), `collateral_damage` (+ rate),
`total_api_calls` (+ mean), `api_docs_uses` (+ usage rate/task), `observation_truncations`
(+ rate/block), `total_output_tokens` (+ mean), and per-turn `TurnRecord`s. Aggregated into
`BenchmarkReport` (ASR + all rates + outcome histogram).

---

## THE BENCHMARK ENTRY POINT (what the GPU run calls)

`localbench.scoring.agentic_exec.benchmark`:

```python
def run_appworld_c_benchmark(
    task_ids: list[str],
    model_factory: Callable[[str], ModelClient],        # task_id -> a model client
    sandbox_factory: Callable[[str], ContextManager[SandboxLike]],  # task_id -> a fresh sandbox
    config: LoopConfig | None = None,
) -> BenchmarkReport
```

It opens a FRESH sandbox per task (context manager → env-host + bwrap torn down per task, matching
the LOCKED "fresh per task"), builds a fresh model client, runs `run_task`, and aggregates ASR +
diagnostic rates. A per-task setup/teardown failure is captured as a `HARNESS_ERROR` row, so one
bad task never sinks the batch. `BenchmarkReport.as_dict()` is JSON-serialisable for persistence.

### Invoking it with a REAL model endpoint (the follow-up GPU step)

Implement one class satisfying `ModelClient` over your OpenAI-compatible chat-completions endpoint
and pass it as `model_factory`; reuse `appworld_sandbox_factory()` unchanged:

```python
from localbench.scoring.agentic_exec.benchmark import (
    run_appworld_c_benchmark, appworld_sandbox_factory,
)
from localbench.scoring.agentic_exec.model_client import ModelResponse, GenerationParams

class ChatCompletionsClient:                      # the ONLY new code the GPU run needs
    def __init__(self, base_url, model, api_key=""): ...
    def complete(self, messages, params: GenerationParams) -> ModelResponse:
        # POST {base_url}/v1/chat/completions with:
        #   messages=messages, temperature=params.temperature, top_p=params.top_p,
        #   seed=params.seed, max_tokens=params.max_output_tokens
        # return ModelResponse(text=choice.message.content,
        #                      finish_reason=choice.finish_reason,
        #                      output_tokens=usage.completion_tokens)
        ...

report = run_appworld_c_benchmark(
    task_ids=[...dev/test ids...],
    model_factory=lambda task_id: ChatCompletionsClient("http://127.0.0.1:8000", "qwen-..."),
    sandbox_factory=appworld_sandbox_factory(),
)
print(report.agentic_success_rate, report.as_dict())
```

The loop, sandbox, diagnostics, and finalize seam are all unchanged between the scripted run and
the real run — only the `model_factory` swaps. (Per the LOCKED plan, the GPU run does smoke 12 →
lite 36 → 96-task on the Qwen ladder + gemma with 2 reruns; that wiring + the actual GPU launch
is the separate follow-up gated on the 5090 and explicit go-ahead.)

---

## EXACT RE-RUN COMMANDS (independent verification)

```bash
# 1) Host-agnostic loop units — run ANYWHERE (Windows Py3.14 OR WSL); no bwrap/appworld/model.
#    Windows:
%LOCALAPPDATA%\Programs\Python\Python314\python.exe -m pytest cli\tests\test_appworld_protocol_c_units.py -q
#    (expect 26 passed)

# 2) Scripted agent THROUGH the loop on the REAL sandbox (GPU-free, model-free). WSL only.
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_protocol_c_scripted.py --json'
#    (expect: 2/2 success: True, ASR 1.000)

# 3) Both as pytest under WSL (real sandbox acceptance + the 26 units):
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_protocol_c_acceptance.py \
       cli/tests/test_appworld_protocol_c_units.py -v -s'
#    (expect: 27 passed)
```

---

## SCOPE NOTE — what this build is NOT (separate follow-ups)
The Protocol C LOOP + scripted-agent proof + diagnostics + benchmark entry point ONLY. NOT done
here (deliberately): loading any LLM / starting a `llama-server`; the real-model GPU benchmark
(smoke/lite/96-task, 2 reruns, orthogonality vs code-proxy/IFBench); scorer/board/registry wiring
(stays weight-0 candidate); the JSON-native BFCL companion track (flagged P2). The `ModelClient`
seam is kept clean so the GPU run is just "implement one chat-completions client and pass it as
`model_factory`."

## Open issues
- **None blocking.** The loop, diagnostics, failure paths, and entry point are proven end-to-end
  through the real sandbox with the scripted agent.
- The scripted agent advertises **0 `api_docs` usage** because it knows the API shapes a priori;
  a real model is expected to consult `apis.api_docs.*`, which the prompt instructs and the
  diagnostics will then report (`api_docs_usage_rate`). This is expected, not a defect — it is
  exactly one of the diagnostics that will characterise real-model behaviour in the GPU run.
- Per-turn output-token counts under the scripted agent are a deterministic char/4 estimate (the
  scripted client reports no usage); a real client returns true `completion_tokens` from usage,
  which the loop already threads through `ModelResponse.output_tokens`.

# AppWorld agentic-axis feasibility proof — `agentic_exec_appworld_lite_v0`

# VERDICT: **NO-GO** for the agentic axis at the configured budget. De-scope agentic from the v1 launch (keep as a CANDIDATE/parallel track only). The harness mechanics are sound and proven against real AppWorld; the **tool-call budget is the blocker** — `max_tool_calls=11` is incompatible with real AppWorld dev tasks (median gold path = **34** calls, p90 = **132**, max = **214**; only **9 of 57 (15.8%)** dev tasks can ever fit 11 single-call turns). This is exactly risk **R4** (the "single most likely thing to invalidate v0") firing on real data. A clean, narrow GO is possible only by re-scoping the protocol/budget (see "What to do next"); that change is a NEW scorecard identity, not a v1 ship.

Date: 2026-06-23. GPU-free, endpoint-free, NON-LLM. No model loaded, no `llama-server` touched, no `git` commit/push. Evidence below is from a hand-scripted deterministic agent driving **real** AppWorld (`appworld==0.1.3.post1`) in WSL Python 3.12, `APPWORLD_ROOT=<appworld-root>`, determinism trio set.

Re-run command (reproduces every number below):
```bash
wsl bash -lc 'cd /mnt/c/path/to/local-bench && source <wsl-venv>/bin/activate \
  && export APPWORLD_ROOT=<appworld-root> PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && python cli/tools/appworld_feasibility_probe.py'
```
Probe script: `cli/tools/appworld_feasibility_probe.py` (self-contained; imports only `appworld` + stdlib).

---

## Point 1 — Protocol drives real AppWorld: **PROVEN**

Drove real dev task `6bdbc26_1` ("How many people follow the artist of the currently playing song on Spotify?", gold answer `20`) to a real PASS using the **exact** seam the adapter assumes: one JSON tool call per turn → synthesize `print(apis.<app>.<api>(**args))` → `world.execute(code)` → capture stdout → parse. NO LLM; the call sequence was hand-scripted from AppWorld's own gold `solution.py`. Real API outputs captured turn-by-turn:

| turn | synthesized program | captured real output (truncated) |
|---|---|---|
| 1 | `print(apis.supervisor.show_account_passwords())` | `[{'account_name': 'amazon', ...}, {'account_name': 'spotify', 'password': 'et7Jy}S'}, ...]` |
| 2 | `print(apis.spotify.login(password='et7Jy}S', username='allison-calhoun@gmail.com'))` | `{'access_token': 'eyJhbGci...'}` |
| 3 | `print(apis.spotify.show_current_song(access_token='...'))` | `{'song_id': 238, 'title': 'The Illusion of Forever', ..., 'artists': [{'id': 24, ...}]}` |
| 4 | `print(apis.spotify.show_artist(artist_id=24))` | `{'artist_id': 24, 'name': 'Liam Palmer', 'genre': 'country', 'follower_count': 20, ...}` |
| 5 | `print(apis.supervisor.complete_task(answer=20, status='success'))` | `{'message': 'Marked the active task complete.'}` |

`world.evaluate()` then returned `success: True`. **The synthesize→execute→capture-stdout loop works end-to-end on real AppWorld.** Confirmed object surface: `world.execute(code)` returns the captured stdout as a **`str`**; `world.apis`, `world.task.instruction`, `world.task.supervisor.email`, `world.evaluate()` all exist and behave as the harness needs. AppWorld runs in in-process library mode (no server) exactly as the install plan determined.

(`complete_task` is the real completion entrypoint — the harness calls it itself on `final_answer`, so it is NOT counted as a model tool call. Verified the answer can be a bare scalar `20` and the evaluator coerces/compares correctly.)

---

## Point 2 — `evaluate()` key map: **AUTHORITATIVE** (resolves plan risk R2, previously `[UNVERIFIED]`)

`world.evaluate()` returns a **`TestTracker`** object (NOT a dataclass; the stub's `StubEvalResult` shape is fictional). `.to_dict()` keys are fixed:

```
['success', 'difficulty', 'num_tests', 'passes', 'failures']
```

Authoritative map:

| key | type | meaning / how the harness must use it |
|---|---|---|
| **`success`** | bool | **THE pass/fail signal.** `True` iff ALL assertions pass (this already INCLUDES the collateral / no-model-changes check). Map directly to `EvalResult.passed`. |
| `difficulty` | int | task difficulty (1–3). Informational. |
| `num_tests` | int | number of assertions evaluated. |
| `passes` | list | assertions that passed, each `{"requirement": str, "label": str}`. |
| `failures` | list | assertions that failed, each `{"requirement": str, "trace": str(python+AssertionError), "label": str}`. |

**Collateral-damage signal (critical):** there is **NO top-level `collateral_damage` key**. Collateral / unexpected-DB-change is encoded as a named assertion **`"assert no model changes."`** that appears in `passes` (when no collateral) or `failures` (when the agent mutated state it shouldn't have). The answer-correctness assertion is **`"assert answers match."`**. So:
- `passed`  ⇐ `eval["success"]`
- `collateral_damage`  ⇐ the `"assert no model changes."` requirement is present in `eval["failures"]` (derive it by requirement-string match; do not invent a boolean key).
- `checks`  ⇐ build from `passes` + `failures` requirement strings.

**Trap — ignore the `label` field.** It is fixture noise, not the signal. Proof: on the SOLVED task, the `"assert answers match."` assertion sits in **`passes`** yet carries `"label": "no_op_fail"`. Truth = which list (`passes`/`failures`) the requirement is in, plus top-level `success`. A harness that keys off `label` will be wrong.

Pass-side vs fail-side, captured from real runs of the SAME task:

SOLVED (`success: True`):
```json
{ "success": true, "difficulty": 1, "num_tests": 2,
  "passes": [ {"requirement": "assert answers match.", "label": "no_op_fail"},
              {"requirement": "assert no model changes.", "label": "no_op_pass"} ],
  "failures": [] }
```
INCOMPLETE — answer never submitted (`success: False`):
```json
{ "success": false, "difficulty": 1, "num_tests": 2,
  "passes": [ {"requirement": "assert no model changes.", "label": "no_op_pass"} ],
  "failures": [ {"requirement": "assert answers match.",
                 "trace": "...AssertionError:  '<<not_given>>' == '20'", "label": "no_op_fail"} ] }
```
Note: with no `complete_task`, the predicted answer is `<<not_given>>` → the answer assertion fails. This confirms the harness MUST call `complete_task(answer=...)` on `final_answer` for the answer check to receive an input (matches the adapter design).

---

## Point 3 — Budget adequacy: **NO-GO** (this is the gate that fails)

Gold-solution `num_api_calls` over the **entire** dev split (read from each task's `ground_truth/metadata.json`; this is AppWorld's own recorded count of underlying API calls for the canonical solution):

| stat | value |
|---|---|
| n (dev tasks) | 57 |
| min | 6 |
| p10 | 8 |
| **median** | **34** |
| **p90** | **132** |
| max | 214 |
| mean | 56.0 |

Feasibility vs harness `max_tool_calls = 11`:

| budget threshold | dev tasks whose gold path fits | % |
|---|---|---|
| ≤ 5 | 0 / 57 | 0% |
| ≤ 8 | 6 / 57 | 11% |
| **≤ 11 (configured)** | **9 / 57** | **16%** |
| ≤ 15 | 15 / 57 | 26% |
| ≤ 20 | 18 / 57 | 32% |
| ≤ 30 | 21 / 57 | 37% |
| ≤ 50 | 37 / 57 | 65% |

Min single-JSON-calls on the task I actually drove to PASS: `6bdbc26_1` (difficulty 1, the **easiest** tier) solved in **4** single-JSON tool calls (excl. `complete_task`) → fits 11 comfortably. But that task is in the bottom ~10% of the distribution. The **median** dev task needs **34** gold calls and **p90 needs 132** — 3× to 12× over the 11-call budget.

**Why the metric is faithful (not a code-style artifact):** AppWorld's gold call counts are driven by the task DATA, not by Python verbosity. The high counts come from **pagination** (e.g. `for page_index in range(0,10): apis.spotify.show_song_library(page_index=...)`) and **per-item detail fetches** (e.g. `for song in library: apis.spotify.show_song(song_id=...)`). A strict one-JSON-call-per-turn agent issues the **same** underlying `apis.<app>.<api>` calls — the adapter synthesizes exactly ONE call per turn with no batching — so the logical-turn count ≈ the gold api-call count. A task that must read 132 paginated/looked-up records genuinely cannot complete in 11 single-call turns. Worked example: task `50e1ac9_1` ("top 4 most-played R&B songs across song/album/playlist libraries", difficulty 2) has a gold path of **132** calls — it sweeps every page of three libraries and fetches each song's genre individually. No protocol-level cleverness collapses that into ≤11 single calls.

**Conclusion:** at the spec's budget, agentic would score ~84% of dev tasks as **`max_tool_calls_exceeded` hard-fails regardless of model capability** — i.e. the axis would measure the budget, not the model. That is a fabricated-failure trap and a NO-GO for v1.

---

## Point 4 — Adapter-vs-reality reconciliation (concrete bugs)

The `agentic_exec/` package was built 100% against `stub_appworld.py`, whose eval/verify shape does **not** match real AppWorld. The protocol mechanics (synthesize→execute→capture, one call/turn, whitelist) reconcile cleanly; the **completion/eval seam does not**. Bugs, with file:line and fix:

**BUG 1 — `world.verify(...)` does not exist on real AppWorld.**
`cli/src/localbench/scoring/agentic_exec/adapter.py:107`
```python
eval_result = self._world.verify(task.task_id, action.answer)
```
Real `AppWorld` has **no `verify` method** (confirmed: `hasattr(AppWorld, "verify") == False`; only `evaluate` exists). The real flow is two calls: `world.execute("apis.supervisor.complete_task(answer=<answer>, status='success')")` then `world.evaluate().to_dict()`. The `RealAppWorld` wrapper (to be written per install-plan §4) must implement this; the adapter seam name `verify` is fine as the wrapper's method, but it must internally do complete_task + evaluate, NOT call a non-existent `world.verify`.

**BUG 2 — success/collateral computation uses fields that don't exist in real eval output.**
`cli/src/localbench/scoring/agentic_exec/adapter.py:111`
```python
success=eval_result.passed and not eval_result.collateral_damage,
```
Real `evaluate().to_dict()` has neither `passed` nor `collateral_damage`. Correct mapping:
- `passed`  = `eval_dict["success"]`  (this ALREADY accounts for the no-model-changes assertion).
- `collateral_damage` = any failure whose `requirement == "assert no model changes."` is in `eval_dict["failures"]`.
- Because `success` already folds in the collateral check, `success and not collateral_damage` would be **redundant at best and contradictory at worst** (a collateral failure makes `success` False anyway; deriving `collateral_damage` separately is only needed for the `collateral_damage_rate` diagnostic + the `COLLATERAL_DAMAGE` vs `VERIFIER_FAILED` failure-reason split in `runner.py:107-111`). The `RealAppWorld.verify` wrapper must populate `StubEvalResult(passed=success, collateral_damage=<derived>, checks=<from passes/failures>)` so `runner.py`'s existing branch logic keeps working unchanged.

**BUG 3 (latent, not blocking) — observation parsing assumes JSON; real AppWorld stdout is a Python-repr/str.**
`world.execute("print(apis...)")` returns the printed stdout as a `str`. For dict/list returns AppWorld prints JSON-looking text that `json.loads` handles, but some returns are Python `repr` (single quotes) or munch objects — the probe falls back to `ast.literal_eval` then raw string. When wiring `RealAppWorld.call_api`, parse defensively (try `json.loads`, then `ast.literal_eval`, then keep the string) before `canonical_observation`, rather than assuming valid JSON. Not a feasibility blocker, but will bite if assumed.

**Reconciled-as-correct (no bug):** the one-call-per-turn invariant, the `print(apis.<app>.<api>(**args))` synthesis, the whitelist check in `execute_tool_call` (`adapter.py:73`), and `complete_task` being harness-invoked (not a model turn) all match reality. The four-seam design is right; only the eval seam's field names/method are wrong.

---

## What to do next

**Decision: de-scope agentic from v1.** Keep `agentic_exec` as a CANDIDATE / parallel track (weight 0, displayed separately — already its intended status). Do NOT freeze the 96-task manifest. The headline v1 stays Knowledge (MMLU-Pro) + Instruction (IFBench) per the locked methodology; agentic does not gate the launch.

**If/when agentic is revived, the budget must change BEFORE any GPU pilot (and it is a new scorecard identity):**
1. **Pick-fitting tasks (cleanest, keeps the 11-call protocol identical):** select the 96 only from tasks whose gold path ≤ ~9 calls. The dev split shows only ~11% (≤8) to ~16% (≤11) qualify; across train+test_normal+test_challenge there may be enough difficulty-1 single-app lookup tasks, but this **narrows the construct to "short-horizon lookups"** and likely fails promotion-gate #3 (spread across families×bands) and #4 (no floor/ceiling) because the hard bands evaporate. Verify the fittable-task census across all splits before committing.
2. **Raise the cap from measured data (changes scorecard id):** set `max_tool_calls`/`max_turns` from the gold p90 (≈130) + margin. This makes long-horizon tasks feasible but (a) explodes per-task wall-time/token cost — the `max_wall_time_per_task_seconds=240` and `token_budget_per_task=6144` caps also need re-derivation, and (b) a 130-turn agentic task on a local GGUF over an OpenAI-compatible endpoint is a very different (and far more expensive) GPU pilot than the spec assumed. Re-cost against "runs in a few hours per model on one RTX 5090" (promotion-gate #7) before adopting.
3. **Add a bounded-batch action (protocol change → new scorecard id):** a single JSON tool that does a bounded fan-out (e.g. "list all pages of library X" or "fetch details for these N ids") in one turn, collapsing pagination/detail-loops. This is the only option that keeps turn budgets sane AND preserves hard tasks, but it changes the protocol (the build spec flags this as a distinct scorecard identity) and needs care so it doesn't become a code-as-action backdoor.

**Whichever path: first fix the adapter eval seam (Bugs 1–2) when wiring `RealAppWorld`**, because the current `verify()`-based success/collateral computation cannot run against real AppWorld at all. The probe in `cli/tools/appworld_feasibility_probe.py` is the regression check for that wiring (it already exercises complete_task + evaluate().to_dict() on a real pass and a real fail).

**GPU pilot prerequisites (only after a budget decision):** the install plan's §6 freeze (identity constants `APPWORLD_VERSION="0.1.3.post1"` + data-tree sha256) + `RealAppWorld` wired with the corrected eval map, then the GPU-gated 12-smoke. None of that should happen for v1.

---

## Boundaries honored
- GPU-free, endpoint-free: no model loaded, `llama-server`/port 8000 untouched, hand-scripted deterministic agent only.
- No edits under `web/`. No `git commit`/`push`. No changes to `cli/runs/` artifacts. No changes to the scorer lane, `top_k`, `_scoring.py`, axes registry, or scorecard logic.
- **Zero edits to the `agentic_exec/` harness** — bugs are reported as file:line for the maintainer, not patched (proving via standalone probe was sufficient; no adapter change was needed to demonstrate the NO-GO). Only additions: `cli/tools/appworld_feasibility_probe.py` and this doc.
- Existing agentic unit tests still green (12 passed) after my additions.

# AppWorld-C smoke findings — the loop is mis-calibrated for thinking models (2026-06-24)

**Status: DECISION REQUIRED (Michael).** The agentic harness is built + gauntlet-passed, but the
first real-model smoke surfaced a config-vs-model interaction bug that blocks a *valid* scored run.
No scored run / manifest freeze has happened and none will until this decision is made.

## TL;DR

- First AppWorld-C smoke (gemma-4-31B Q4, 1 dev task, **locked** loop config) = **ASR 0,
  harness-dominated**. The model never got to *attempt* the task on its merits.
- Root cause is **harness CONFIG mis-calibration for native-thinking models**, NOT proven model
  incapacity. The locked per-turn output cap (`1024`) is smaller than gemma's *thinking* on a single
  turn, so 10 of 24 turns were truncated mid-thought with no code block emitted → a format-failure
  cascade → 24-turn cap hit → ASR 0.
- **This affects every model we would score**: gemma is native-thinking, and the Qwen ladder is the
  `capped-thinking` lane. A 1024-token turn cap starves all of them on a code-as-action loop.
- The smoke did exactly its job (find loop-vs-real-model bugs before any scored GPU spend). Per the
  launch plan, smoke/lite live on the **dev split** precisely so we can calibrate here.
- I ran a **Tier-1 diagnostic re-smoke** (output cap 3072, context 40960) to separate "starved
  harness" from "model can't do it." **Result + my recommendation: see §5 / §7.**

## 1. What ran (the baseline smoke)

- Task: `4ec8de5_3` (frozen dev smoke subset, `manifest_hash 178f7c90…`, size 1).
- Server: gemma-4-31B-it-Q4_K_M.gguf on llama-server, `-c 20480`, single slot, greedy (temp 0, seed 0).
- Loop: **LOCKED** `LoopConfig` — `max_turns=24`, `max_output_tokens_per_turn=1024`,
  `max_observation_chars=8000`.
- Artifact: `cli/runs/agentic/gemma4-31b-Q4_K_M.smoke.run1.json`.

Report: `agentic_success_rate=0.0`, `cap_exceeded_rate=1.0`, `format_failure_rate=0.458`,
`runtime_error_rate=0.462`, `syntax_error_rate=0.0`, `mean_turns_used=24`, `mean_blocks_run=13`,
`mean_output_tokens=19080`. Early-stop fired: `near_zero` + `harness_dominated`
(`harness_failure_share=1.00`).

## 2. Diagnosis (per-turn evidence)

Per-turn record (`…run1.json` → `report.results[0].diagnostics.turns`):

- **10 of 24 turns: `finish_reason="length"`, `output_tokens=1024`, `had_block=False`,
  `format_error="length"`** (turns 1,2,4,10,16,17,20,21,22,23). The model spent the entire 1024-token
  budget *thinking* and was cut off before it could emit the closing ```python fence. The loop
  (correctly, per its contract) treats a truncated turn as a recoverable format failure and injects a
  corrective observation — but the next turn does the same thing. Wasted turns accumulate.
- 1 more format failure (turn 3) was `finish_reason="stop"` with no block ("missing").
- The 13 turns that *did* emit a block: ~46% threw a runtime error. Whether that is genuine API
  misuse or downstream incoherence from the truncation cascade can't be separated on one task (see §5).
- `syntax_error_rate=0.0` — when gemma emits code, it is syntactically valid. The failure is *getting
  the code out*, not writing it.

**Coupled secondary risk — unbounded history.** `protocol_c_loop.py` appends *every* assistant turn
(raw, including thinking) to `messages` with **no windowing/pruning** (only observations are capped at
8000 chars). With `mean_output_tokens=19080` accumulating into a 20480-token context, the transcript
approaches/exceeds the window late in the task; llama.cpp's default context-shift then silently drops
the *oldest* tokens — i.e. the task instruction and the fetched API docs — which would explain the
late-turn collapse (turns 16–23 are almost all truncations). Raising the output cap **without**
addressing history makes this *worse* (history grows faster). The two issues are coupled.

## 3. Why this matters (construct validity)

The oracle's central launch risk was: *"a beautiful, secure column that measures Protocol C harness
artifacts (parser brittleness, cap/timeout, format compliance) instead of interactive API-coding
skill."* The baseline smoke is currently measuring exactly that for a thinking model. Publishing a
scored AppWorld-C column off the locked config would mis-measure every thinking model as near-zero —
worse than not shipping the column. The fix has to move the failure mode from "harness friction" to
"genuine API-coding attempts" before any number is trustworthy, even as a 0-weight candidate.

## 4. The two-tier fix framing

There are two *separable* levers, with very different risk/authority profiles:

- **Tier 1 — CONFIG calibration (low-risk, dev-split-sanctioned, no contract change).** Raise the
  per-turn output cap so thinking isn't truncated; raise server context so a full trajectory fits.
  These are budgets, not loop logic — the launch plan explicitly calibrates smoke/lite on dev. I added
  an **additive** `--max-output-tokens` / `--max-turns` override to the funnel CLI (locked defaults
  preserved; the frozen subset hash is unchanged), so this needs no edit to the locked `LoopConfig`.
- **Tier 2 — STRUCTURAL fix (changes loop logic + the determinism/trace contract → needs your
  go-ahead + an oracle red-team).** Make the loop **thinking-aware**: do not feed prior turns' raw
  chain-of-thought back into history. Keep each assistant turn's *action* (the parsed ```python block)
  + any non-thinking answer text; drop the reasoning span before appending to `messages`. This is
  standard practice for running reasoning models in agent loops and it fixes *both* root causes at
  once (compact history → no context-shift; generous fresh thinking each turn). The delimiters are
  already pinned in `reasoning_registry.py`:
  - Qwen: reasoning closes at `</think>` → keep text after the final close.
  - Gemma 4: reasoning is the span `<\|channel>thought\n … <channel\|>` → keep everything outside it.
  - The loop's `block_parser` already locates the code block, so history can store the normalized
    block directly.
  Cost: the gauntlet's trace-replay reference traces would need **re-recording** (the stored message
  sequence changes), and it should be oracle-red-teamed before it touches the locked harness. The
  determinism *contract* (greedy, fixed seed, deterministic-from-frozen-artifacts) is preserved; only
  the reference fixtures change.

## 5. Tier-1 diagnostic re-smoke — RESULT

Config: same task `4ec8de5_3`, **`--max-output-tokens 3072`**, server `-c 40960` (KV unquantized, VRAM
~27.7/32.6 GB), greedy. Artifact: `cli/runs/agentic/gemma4-31b-Q4_K_M-diag3072.smoke.run1.json`.
Purpose: a DIAGNOSTIC probe (not a scored config) to test whether un-starving the thinking budget
shifts the failure mode from harness-friction to genuine attempts.

**Result — the failure mode shifted from harness-friction to a genuine on-merits attempt.**

| metric | cap 1024 (baseline) | cap 3072 (diagnostic) |
|---|---|---|
| outcome | `cap_exceeded` | **`failure`** (finalized, evaluate=False) |
| cap_exceeded_rate | 1.00 | **0.00** |
| mean_turns_used | 24 | **13** |
| format_failure_rate | 0.458 | **0.231** |
| runtime_error_rate | 0.462 | 0.400 |
| mean_output_tokens | 19080 | 12050 |

- The model **finalized cleanly** (`finalize_error=None`) at turn 13, having made **32 real API calls**,
  **5 API-doc lookups**, and run **10 code blocks** — then AppWorld's `evaluate()` returned False.
  gemma genuinely attempted and **failed task `4ec8de5_3` on its merits**, the opposite of the
  baseline's truncation cascade. This is the loop measuring *skill*, not *friction*.
- Residual friction is minor + recoverable: of the 3 remaining format failures, **2 were
  `multiple_blocks`** (verbose thinking emitted >1 code block in a turn — a recoverable Protocol-C
  violation; the parser correctly detected them and the loop injected a correction) and **1 was a
  `length` truncation** (one turn's thinking still exceeded 3072 → candidate to bump the cap to ~4096
  for the frozen config).
- **Caveat on the early-stop flag:** it still printed `harness_dominated` / `near_zero`. That is an
  **n=1 artifact** — the `harness_dominated` condition counts a task as harness-tainted if its
  trajectory contained *any* parser/format/runtime error, even though this task ended in a genuine
  `failure` *outcome*. On a single task that resolves to `harness_share=1.00`. The heuristic should
  key on terminal outcomes (`cap_exceeded`/`no_final_answer`/`harness_error`) and/or require a larger
  sample before firing; flagged as a metric-design follow-up (it would otherwise mislabel a
  genuinely-attempted-but-failed task as "harness friction").

**Read:** the locked 1024 cap was the dominant bug; sizing the per-turn budget for thinking turns it
into a working loop.

### 5b. 6-task wide-smoke (gemma, cap 3072) — the loop generalizes; gemma is genuinely weak

Frozen 6-task dev subset (`manifest_hash 88621a43…`), cap 3072, ctx 40960. Artifact
`cli/runs/agentic/gemma4-31b-Q4_K_M-diag3072-wide.smoke.run1.json`. **ASR 0/6**, but the *outcomes*
are the story:

| outcome | count | meaning |
|---|---|---|
| `failure` (finalized, evaluate=False) | **5** | genuine on-merits attempt — the loop measured skill |
| `cap_exceeded` | 1 | one hard task (396c5a2_1) ran the full 24 turns |

Aggregate: `format_failure 0.211`, `runtime_error 0.244` (both far below the cap-1024 baseline's
~0.46), `mean_turns 9.5`, `mean_api_calls 13.3`. Per task the model genuinely engaged (10-29 API
calls on the failures, clean finalize each).

**Conclusions:**
1. **The harness is validated.** 5/6 are genuine attempts; the loop measures interactive API-coding
   skill, not Protocol-C friction. Michael's core requirement ("be able to score agentic capability")
   is met with a working, secure, judge-free loop.
2. **gemma-4-31B Q4 genuinely cannot solve AppWorld dev (0/6)** — an honest capability-frontier
   result, not an artifact. (Michael, awake: "gemma is weak at agentic tasks; qwen will do better.")
3. **Metric bug — `harness_dominated` over-flags.** It reported `harness_share=1.00` by counting any
   trajectory with *any* format/runtime error, but only **1/6** tasks ended in a harness *outcome*
   (`cap_exceeded`); the true harness-failure share is **0.167**. The early-stop condition must key on
   terminal outcomes (`cap_exceeded`/`no_final_answer`/`harness_error`), not error-presence, or it
   mislabels genuine-attempt-but-failed tasks as friction. **Fix before any scored run.**
4. **Open — discrimination.** gemma floors at 0; whether the column *ranks* needs a contrasting
   system. **Qwen3.6-27B Q4_K_M wide-smoke running** (`brxjg2ojv`, identical config) to test it.

## 6. Decision options (Michael)

- **A. Tier-1 is enough → agentic stays in v1.** If the re-smoke shows the format-failure cascade
  gone and the model making real attempts, freeze a retuned AppWorld-C manifest (output cap + context
  as pins), run lite (36 dev tasks, 2 systems) to confirm it's measuring skill not artifacts, then the
  scored funnel. Agentic ships as the validated 0-weight candidate.
- **B. Tier-2 needed → invest in the structural fix.** If Tier-1 still shows harness domination
  (thinking > 3072, or context-shift degeneration), implement thinking-aware history (oracle-red-team
  first, re-record gauntlet traces, re-smoke). Higher quality, but it delays launch and touches the
  locked harness.
- **C. Ship v1 WITHOUT a scored agentic column** (oracle-sanctioned fallback). Keep AppWorld-C as an
  "under validation" methodology note; headline stays Knowledge+Instruction. Agentic becomes a
  fast-follow. This is explicitly the recommended path *if* validation doesn't cleanly pass — "a bad
  candidate column is worse than none."

### 6b. Two-system contrast (gemma Q4 vs Qwen Q4, identical config) — the field FLOORS at 0

| metric | gemma Q4 | Qwen Q4 |
|---|---|---|
| ASR | **0/6** | **0/6** |
| genuine `failure` outcomes | 5/6 | **6/6** (0 cap_exceeded) |
| format_failure_rate | 0.211 | **0.071** |
| runtime_error_rate | 0.244 | **0.076** |
| mean_turns / blocks | 9.5 / 7.5 | 14.2 / 13.2 |
| mean_output_tokens | 7087 | **1600** |

**Both board ship-rung models score 0/6.** Qwen is markedly *better-behaved* (reached a genuine final
answer on all 6, ~3× fewer format failures, ~3× fewer runtime errors, more persistent) but **not
better-scoring** — the tasks are simply beyond a 30B Q4 local model. The harness is now **doubly
validated**: 11 of 12 trajectories across two model families are genuine on-merits `failure`s, so the
loop measures interactive API-coding skill, not Protocol-C friction.

**Confound to verify:** Qwen ran far terser (1600 vs gemma's 7087 output tokens; ~113 tok/turn) —
likely under-engaging its `<think>` channel in the raw-chat loop, i.e. effectively answer-only while
gemma thinks verbosely. The two models may be in *different reasoning modes* in the loop — a
lane-consistency nuance to confirm before any scored/displayed agentic numbers (relates to the
Tier-2 thinking-aware design).

## 6c. RECOMMENDATION

The harness is **built, secure, judge-free, and validated** — Michael's requirement ("be able to
score agentic capability; don't just cut it") is **met**. But on the current local field (both board
ship-rung models = 0/6) the column has **no ranking discrimination**, which is exactly the launch
plan's `near_zero` "nothing to rank" signal.

- **Recommended: do NOT ship AppWorld-C as a v1 *ranking* column** (an all-0 column ranks nothing and
  reads as filler). Instead ship the **validated harness + the honest result** on the methodology /
  limitations page + candidate data: *"AppWorld-C interactive API-coding ASR — local 30B Q4 models
  score 0%; harness is real, sandboxed, judge-free, reproducible; no ranking discrimination at this
  capability tier yet."* Promote to a board column once we have **discriminating** models (stronger
  quants, frontier anchors, or as local models improve). This loses nothing — the harness work is
  done and documented, and it keeps the board honest.
- **Pre-req regardless:** fix the `harness_dominated` metric (key on terminal outcomes, §5b/3) before
  any scored run, and resolve the Qwen thinking-engagement confound (lane consistency).
- **Optional, Michael's call:** one **Qwen Q8 / frontier-anchor probe** to confirm the frontier —
  does *anything* crack AppWorld-C? If a stronger model scores >0 there's a discrimination story worth
  a wider-field column; if even Q8 floors, that cements "validated-but-no-ranking-yet." Not
  v1-blocking; ~45 min GPU.

*(Superseded framing: the earlier §6 A/B/C options were written against the single-task diagnostic
before the 2-system floor was known; 6c is the operative recommendation.)*

## 6d. UPDATE — thinking ENGAGED (harness fix) -> the axis DISCRIMINATES

The first Qwen-with-thinking attempt (server `enable_thinking` flag only) came out byte-identical to
no-thinking. Root cause: `build_initial_messages` kicked off from a **system-only** history, which
Qwen cannot generate from (turn 1 errored -> 0 tokens -> poisoned trajectory; thinking never engaged;
gemma happened to tolerate system-only). Fixed the harness with a standard `user` "Begin." kickoff
(`prompt.py`; unit test updated + passing). Re-ran:

| metric | Qwen no-think | Qwen THINK+kickoff |
|---|---|---|
| ASR | 0/6 | **1/6 (0.167)** |
| solved | none | `4ec8de5_3` (13 turns, 6001 output tok) |
| format_failure_rate | 0.071 | 0.014 |
| mean_output_tokens | 1600 | 2219 (thinking now genuinely engaged) |

**Hypothesis confirmed: Qwen-with-thinking solves a task gemma + no-think-Qwen both fail.** First
DISCRIMINATION on the axis: gemma 0/6, Qwen-no-think 0/6, Qwen-think 1/6 — the harness measures genuine
skill AND can rank when thinking is engaged. This REOPENS agentic as a potentially viable
(low-but-discriminating) v1 column, IF runs are thinking-engaged across the board.

**Clean comparison DONE (gemma re-run, kickoff + thinking, identical config):** gemma **0/6** vs Qwen
**1/6**. On `4ec8de5_3` (the task Qwen solved) gemma spent 20 turns / 49 API calls / 18k tokens and
still failed; gemma also runs messier (format-fail 0.27, runtime-err 0.39 vs Qwen 0.01 / 0.07). So the
spread holds and is clean: **Qwen3.6-27B Q4 > gemma-4-31B Q4 on AppWorld-C, both thinking-engaged.**
n=6 dev tasks (1 task ~= 16.7pp) — a PREVIEW signal, not yet a publishable ranked number.

Open before any scored agentic column: (b) decide the
thinking-engagement mechanism for the FROZEN config (the server `--chat-template-kwargs enable_thinking`
flag works but is fragile across conversation shapes; passing `chat_template_kwargs` per-request from
the client is more robust + model-explicit); (c) fix the `harness_dominated` metric (still over-flagged
0.80 despite 1 success + 5 genuine failures, 0 harness outcomes); (d) re-record the WSL gauntlet traces
(the kickoff changed message structure); (e) lite (36 dev tasks, 2 systems) to size the real spread
before any 96-task scored pass.

## 7. Guardrails respected

- No scored run, no manifest freeze, no registry change — AppWorld-C remains unregistered / weight-0.
- The locked `LoopConfig` defaults are untouched; the CLI override is additive and dev-split-only.
- `board_v1.json`, the scorer, and the site renderer were not touched by this work.
- GPU was freed between runs; the server is up only for the active diagnostic.
- No commits/pushes.

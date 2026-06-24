# Agentic axis — final build spec v0 (`agentic_exec_appworld_lite_v0`)

Date 2026-06-23. Source: GPT-5.5 Pro (oracle) consult `localbench-agentic-harness-robust-design`,
synthesized + extended by the CLI agent (Claude). **This is the BUILD AUTHORITY Codex builds
from.** `agentic-exec-design.md` remains the rationale; THIS is the spec. Status: CANDIDATE
(weight 0) until the promotion gate passes — never auto-wired into the Intelligence Index.

## Verdict (oracle, adopted)
Build `agentic_exec_appworld_lite_v0`: **AppWorld substrate**, **local-bench JSON action
protocol** (NOT AppWorld code-as-action), **deterministic AppWorld final-state verifier**,
**96 scored tasks**, candidate-only until the promotion gate passes.

## The five decisions that matter
1. **AppWorld is the substrate.** Local-runnable, execution-verified, stateful, multi-app,
   collateral-damage checks. NOT saturated overall (GPT-4o ~49% normal / 30% challenge at
   release). Caveat: not contamination-proof — treat public scored tasks as trainable over
   time; mitigate with private sentinels + spot reruns. Do NOT republish AppWorld hidden data.
2. **Wrap AppWorld APIs behind a strict JSON action protocol — do NOT run code-as-action.**
   Code-as-action conflates raw Python coding with agentic planning. Exactly one JSON object
   per assistant turn: `{"type":"tool_call","tool":"app.api","arguments":{}}` or
   `{"type":"final_answer","answer":...}`. No markdown, no extra prose.
3. **No native function-calling, no grammar-constrained JSON in the scored lane.** Plain-text
   JSON output; a model that cannot emit valid JSON loses points (exposed as
   `invalid_json_rate` / `schema_error_rate`). Those features are dev-smoke only — using them
   would make the server scaffold part of the benchmark.
4. **96 scored tasks** = 4 families × 3 bands × 8/cell (±~10pp worst-case binomial CI @ 50%
   ASR). 36-lite + 12-smoke tiers. Don't start with full AppWorld; don't go 120–160 until
   post-promotion calibration.
5. **Scaffold identity is part of the scorecard.** Same model under code-as-action vs JSON vs
   ReAct vs grammar-constrained = a different measurement. Hash prompt, parser, tool schema,
   budgets, adapter, AppWorld version + bundle, llama.cpp version, GGUF, chat template,
   tokenizer.

## Construct
> Can this local GGUF model plan and complete a multi-step stateful tool task through a fixed
> deterministic JSON tool protocol, scored only by final environment state + exact artifacts?

NOT "can it write Python that happens to call APIs."

## Families (4) × bands (3)
Families: `read_lookup_exact_answer`, `single_app_state_mutation`, `cross_app_workflow`,
`policy_collateral_sensitive`.
Bands: `appworld_level_1` (A) / `level_2` (B) / `level_3` (C).
Per cell = 8 tasks: **5 test_normal + 3 test_challenge** (INVERT for the policy family:
3 normal + 5 challenge).
v0: hand-author the manifest — label ~150 candidate AppWorld tasks once, pick 96, **FREEZE the
manifest BEFORE running the model ladder** (anti-p-hack). No classifier cathedral.

## Runtime / lane (tighter than Core Text — these are STARTING values; see Build-time validations)
```yaml
axis_id: agentic_exec_appworld_lite_v0
context_size: 32768
max_assistant_turns_per_task: 12
max_tool_calls_per_task: 11
max_generated_tokens_per_turn: 768
max_generated_tokens_per_task: 6144
max_observation_chars_per_tool: 12000
max_api_doc_chars_per_call: 8000
max_wall_time_per_task_seconds: 240
temperature: 0
top_k: 1
top_p: 1
min_p: 0
seed: fixed_integer
parallel_requests: 1
```

## Tool set
Expose ONLY: `api_docs.search`, `api_docs.get`, whitelisted `<app>.<api>`, `final_answer`.
(API docs are on-demand tools — do NOT dump all 457 AppWorld APIs into context.)
NEVER expose: `python.exec`, shell, filesystem, network, arbitrary HTTP, SQL console, env
reset, evaluation/ground_truth/setup APIs. The harness calls `supervisor.complete_task` itself
on `final_answer` — don't make the model waste a turn on benchmark ceremony.

## Scoring
Primary: **Agentic Success Rate** = % tasks where ALL required final-state assertions pass AND
no collateral assertion fails. Wilson 95% CI. Family/band subscores.
Diagnostics (displayed, NOT composited): `invalid_json_rate`, `schema_error_rate`,
`avg_tool_turns`, `avg_generated_tokens`, `cap_hit_rate`, `collateral_damage_rate`,
`recovery_after_tool_error_rate`. Show cost; never put efficiency in the main score.

## Failure policy
Hard-fail immediately: `finish_reason==length`; global token cap hit; max-turn cap without
`final_answer`; forbidden tool; ground-truth/eval/setup access; host fs/network/shell;
canary misuse; destructive action outside the AppWorld API wrapper; verifier fail; collateral
assertion fail.
Malformed JSON/schema: **first** malformed output → deterministic error observation, consume one
turn; **second** → hard fail. Tool runtime error → deterministic error observation, model may
recover within remaining budget. Same invalid call+args twice → `loop_guard` hard fail.

## Determinism
`PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C.UTF-8`. One model loaded at a time, no concurrent task
execution per server, no speculative decoding in scored runs. Fresh AppWorld task world per
task (reset DB + time + conversation + tool state). Pin + hash: appworld version, bundle hash,
Python, OS/container digest, localbench commit, adapter commit, task manifest, prompt, tool
schema, verifier, llama.cpp version, llama-server args, GGUF SHA256, chat template, tokenizer.
`scorecard_hash` over the scaffold identity; separate `run_hash` over model artifact + quant +
chat template + transcript hashes.

## Anti-gaming (game-RESISTANT, not game-proof — say so publicly)
Public pack = task IDs, family/band labels, budgets, prompt/tool-schema/adapter/scorecard
hashes, ASR + diagnostic definitions. **Do NOT republish AppWorld hidden data / decrypted
bundles.** 24 private sentinels (same family/band mix, trust audits only, not in public score;
display pass/warning/fail/not-run beside public ASR). Canaries in system prompt / irrelevant
docs / tool outputs / hidden metadata → fail on copy-to-answer, pass-as-arg, claimed hidden
access, action selection, artifact emit. One frozen public surface + one hidden paraphrase
(manually reviewed, hashed — NOT LLM-generated at scoring time) for sentinel/spot reruns. Hidden
spot reruns for top/suspicious runs → label "public-pack overfit suspected", never silently
alter public ASR.

## >>> CLI-agent value-add: BUILD-TIME VALIDATIONS — MEASURE, DO NOT ASSUME <<<
These are MY additions on top of the oracle spec. The oracle's budgets are reasonable defaults,
but three are EMPIRICAL questions that must be answered with DATA during the scripted-agent +
smoke phase, BEFORE freezing the 96-task scorecard. These are why build steps 3 + 5 are GATES.

1. **Tool-call budget vs AppWorld task feasibility (HIGHEST RISK).** AppWorld is natively
   code-as-action — its tasks may assume the agent writes Python loops issuing MANY API calls
   per "turn". Our one-call-per-turn JSON protocol with an 11-tool-call cap could make
   bulk-operation tasks INFEASIBLE (a task needing 40 contact lookups cannot fit in 11 calls).
   ACTION: in the scripted-agent phase, write deterministic gold solutions for 2–3 tasks per
   family and COUNT the API calls each needs. Set `max_tool_calls_per_task` from that
   distribution (e.g. p90 + margin) OR select only tasks whose gold solution fits the cap. Do
   NOT freeze the manifest until task feasibility under the JSON protocol is proven. If most
   AppWorld tasks need >>11 calls, escalate: raise the cap, add a bounded-batch action, or
   reconsider the protocol. **This is the single most likely thing to invalidate v0.**
2. **Per-turn token budget vs reasoning models.** 768 tokens/turn may be too tight for a
   thinking local model (Qwen3.6, gemma-4 thinking) to reason AND emit a valid tool call in one
   turn — it could truncate mid-think (`finish_reason==length` → hard fail), scoring agentic
   ability as a budget artifact. ACTION: in smoke, run a reasoning model and measure
   tokens-to-first-valid-action. If 768 truncates legitimate reasoning, raise the per-turn cap
   or add a per-turn think sub-budget (like Core Text capped-thinking) with force-close; keep
   the GLOBAL per-task cap as the real bound.
3. **Format-failure floor.** Weak models may score ~0 on JSON-format failures, not agentic
   inability. The one-retry + `invalid_json_rate` diagnostic + floor-heavy monitor give
   visibility, but in smoke confirm a weak-but-capable model isn't ENTIRELY format-gated. If
   format dominates all failures for non-weak models, harden the protocol prompt (clearer spec,
   one in-context example) — NOT grammar-constrained decoding (that defeats the construct).

Report the measured numbers; final budgets are set from data, not assumed.

## Saturation / discrimination monitor (per release — the standing gate)
Anchor ladder every scorecard: weak 7–9B, mid 14–17B, strong 30–32B, optional best 70B-quant
that fits 5090 policy, + one frontier API model as diagnostic-only (not ranked).
Flag **saturated** if: top-3 local >85% ASR; top-vs-mid spread <8pp with overlapping CIs; >25%
of tasks solved by every anchor; any family×band cell with top >90% & median >70%; L1 >90% for
top local. Flag **floor-heavy** if: strongest local <15% ASR; >35% of tasks solved by none;
format failures dominate for all but the weakest. On saturation → new identity
`...v0.2`, never mutate a live scorecard.

## Build order (oracle, adopted) — each step is a GATE
1. **Parser/protocol** — strict JSON parser, schema validation, one-retry rule, failure reasons + unit tests.
2. **AppWorld adapter** — load task, expose whitelisted APIs, execute JSON tool call,
   canonicalize observation (sorted keys, stable floats, deterministic truncation), final-answer → completion/eval.
3. **Scripted agent (non-LLM)** — deterministic runner solving 2–3 known dev tasks → proves the
   env+verifier path AND yields the API-call-count data for validation #1.
4. **Scoring** — ASR, Wilson CI, family/band subscores, diagnostics, transcript hash.
5. **12-task smoke** — one weak + one strong local model → confirm not all-zero, not
   all-format-fail, AND gather validation #2/#3 data.
6. **36-task lite** — harness stabilization + repeated-run determinism.
7. **96-task candidate** — freeze scorecard ONLY after smoke/lite evidence + the 3 validations resolved.

## Promotion gate (candidate → counts toward the Intelligence Index)
1. Verifier validity ≥95% human-audit agreement. 2. Repeated-run stability within pre-registered
CI (≈3pp or ≤2 task flips on 96). 3. Meaningful spread across weak/mid/strong locals (lower CI
clears spread across ≥3 families × 3 bands). 4. No floor/ceiling. 5. Not highly redundant with
Core Text (low partial correlation with K+I). 6. Gaming audit pass. 7. Runs in a few hours per
model on one RTX 5090. Until ALL pass: candidate, displayed separately, weight 0.

## Defer (do NOT build now)
Bespoke task generator; browser/GUI/WebArena; SWE-bench/coding-exec; community submissions;
sentinel automation beyond a placeholder; dynamic paraphrase; IRT; LLM trajectory analysis;
per-model prompt tuning.

## Biggest risk (oracle): the scaffold dominates the score
Invalid if the board mostly measures Python coding (code-as-action), native FC template compat,
grammar-constrained decoding, parser quirks, per-model wrapper quality, AppWorld memorization,
or post-hoc task p-hacking. Avoid: one protocol for all models; no arbitrary Python; pre-freeze
manifest before the ladder; scorecard hash separates scaffold from model identity; diagnostics
beside ASR; candidate until spread proven; don't promote if K+I predicts ~all agentic variance.

## File structure (oracle) — new axis package
```
localbench/scoring/axes/agentic_exec/
  __init__.py registry.py config.py types.py score.py
  appworld_lite/
    __init__.py axis.py runner.py appworld_adapter.py tool_registry.py
    protocol.py parser.py verifier.py manifest.py observations.py hashing.py
    prompts.py diagnostics.py sentinels.py
    prompts/{system.md, tool_protocol.md, recovery_invalid_json.md}
    manifests/{appworld_lite_smoke_v0.yaml, _36_v0.yaml, _96_v0.yaml}
    schemas/{assistant_action.schema.json, scorecard.schema.json, transcript.schema.json}
tests/scoring/agentic_exec/
  test_parser.py test_protocol_schema.py test_appworld_adapter_smoke.py
  test_score_asr.py test_hash_stability.py test_failure_policies.py
  fixtures/{scripted_success_transcript.json, malformed_json_transcript.json, forbidden_tool_transcript.json}
```
Registry entry: `status="candidate"`, `primary_metric="agentic_success_rate"`,
`requires_gpu=True`, `requires_network=False`, `uses_llm_judge=False`, weight 0.

## Codex build instructions (division of labor — respects Codex sandbox + GPU gate)
- **Codex builds CODE + unit tests** under `localbench/scoring/axes/agentic_exec/`. Zero file
  overlap with the Lane B registry work (different package).
- **AppWorld install needs network → Codex's sandbox blocks it** (same as the gemma tokenizer).
  So: build the parser/adapter/scoring/verifier + unit tests against a **small stub/fixture that
  mimics the AppWorld API + verifier shape** (so tests are hermetic). The REAL AppWorld install,
  the scripted-agent run against real AppWorld, and ALL LLM smoke/lite/candidate runs are
  **Claude's** (network + GPU). Flag clearly what you stubbed so Claude wires the real thing.
- Apply your own xhigh judgment; where you disagree with a budget/policy, FLAG it with reasoning
  before finalizing — do not silently change it.
- Treat the 3 build-time validations as first-class deliverables: instrument the scripted-agent
  + smoke paths to REPORT measured API-call counts, tokens-to-action, and failure-mode breakdown.
- Do NOT run the GPU model ladder. Stop at hermetic unit tests green + the scripted-agent design
  ready for Claude to run against real AppWorld.
```
```

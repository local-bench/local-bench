# agentic_exec axis — design + AppWorld-lite pilot (oracle-informed)

Date 2026-06-23. Synthesis of the two GPT-5.5 Pro (oracle) reviews (strategy + execution plan),
weighed by the CLI agent. **Status: CANDIDATE / design + pilot only. NOT headline. NOT a v1
blocker. Parallel track, design-only during P0.** Promote only through the gate below.

## Why this exists
Tool-use/agentic is a first-class capability now, but our current "agentic" axis = BFCL, which is
experimental/gameable (a function-calling FORMAT profile). Rename BFCL -> `function_calling`
(diagnostic). Build a separate, credible `agentic_exec` axis.

## The hard constraint -> the design
Judge-free (no LLM-as-judge anywhere in scoring). So the ONLY defensible agentic measurement is
**execution / final-state verification**: correctness = the final environment state + exact
artifacts, graded deterministically. Trajectory quality ("good plan", "sensible recovery") and
LLM-simulated users are OUT (they need subjective judgment).

## Construct (what we measure — and what we DON'T claim)
> A model's ability to complete multi-step, stateful, tool-mediated tasks in a DETERMINISTIC local
> environment, under a fixed tool protocol + turn budget + token budget, scored ONLY by final state
> and exact artifacts.

Do NOT claim it measures "autonomy", "real-world agency", or "computer use".

## Harness (one canonical scaffold)
- Model receives: system prompt, task, tool schemas, observations.
- Model emits either a `tool_call` JSON or a `final_answer` JSON (a model that can't emit valid JSON
  loses — that's part of tool-use capability; no special wrappers per model).
- Tool calls execute in a deterministic Python environment. No internet. No LLM user-sim. No hidden
  scoring prompt. No trajectory judge.
- All task initial states + target assertions are hashed into the scorecard.
- Separate LANE + budget (agentic needs a global task budget, not unlimited per-turn thinking):
  8-12 tool turns, fixed context, greedy top_k=1, global generated-token cap per task, per-turn
  cap, smaller per-turn thinking cap than the Core Text lane; cap-hit = task failure.

## Scoring
- **Primary: Agentic Success Rate** = % tasks where ALL final-state assertions pass AND NO forbidden
  collateral assertion fails.
- Hard-fails: wrong/missing/forbidden state change; invalid final answer; max-turn/token-cap
  exceeded; unrecoverable malformed tool call; forbidden/destructive tool; canary misuse.
- **Display but do NOT composite (v1):** invalid-tool-call rate, schema-error rate, avg tool turns,
  avg tokens, timeout/cap-hit rate, collateral-damage rate, recovery-after-tool-error rate.
- Do NOT put efficiency in the main score (models learn recklessness). Measure success, then show cost.

## Task families (for a bespoke world LATER — 120-160 scored + a `lite` tier)
1. Stateful business APIs (orders/refunds/inventory/policy compliance).
2. Cross-app personal workflow APIs (calendar/email/notes/files, with forbidden-action constraints).
3. Local doc + SQLite tools (search/reconcile/compute/update).
4. Adversarial/collateral-damage (irrelevant tools, forbidden writes, prompt-injection in tool
   outputs, canaries, permission boundaries).
NOT code-generation (that's the separate coding-exec axis).

## PILOT FIRST: AppWorld-lite (the actual next step)
Do NOT build the bespoke 120-160 task world yet. **Pilot AppWorld-lite** to validate the construct
cheaply BEFORE investing:
- AppWorld = best off-the-shelf match (local API world, programmatic state/unit-test verification,
  collateral-damage checks). Use a curated subset ("AppWorld-lite") or borrow its design.
- Pilot deliverables (DESIGN/SCAFFOLD only — no scored campaign, no promotion):
  1. AppWorld-lite scope (which app/task subset).
  2. The `tool_call`/`final_answer` JSON protocol draft.
  3. Final-state verifier shape (assertions -> pass/fail, deterministic).
  4. Invalid-tool-call / malformed-JSON failure policy.
  5. No-LLM-judge scoring rule (Agentic Success Rate).
  6. The promotion-gate checklist (below).
  7. A few hand-authored smoke tasks to confirm it RUNS + DISCRIMINATES a weak vs strong local model.
- If the pilot does NOT separate models -> do not promote; revise. (Avoid τ²-bench's LLM-sim user,
  SWE-bench (contamination), WebArena/GAIA (later), ToolBench/ToolEval (LLM judge).)

## Non-gameability (public + reproducible can only be game-RESISTANT)
Parameterized task generators; public frozen scored seed pack; PRIVATE sentinel generated from the
same template families (trust signal only, not the score); canary strings in tool outputs;
paraphrased task surfaces; hidden-after-upload spot reruns; task-family balance (can't win by
learning one API pattern); scorecard hash over generator version, seeds, tool schemas, verifier
code, scaffold prompt, budgets.

## Promotion gate (stronger than "separates a small ladder") — all required to PROMOTE
1. Verifier validity: >=95% human-audit agreement on pass/fail (stratified sample; no systematic
   false passes).
2. Reproducibility: repeated runs stable within pre-registered CI.
3. Local discrimination: lower 95% CI bound clears a meaningful spread across >=3 families x 3 size bands.
4. No floor/ceiling (weak locals not all ~0; strong not all saturated).
5. Independence: not just instruction-following in disguise (low partial correlation with K+I).
6. Gaming audit: prompt/schema/parser-targeting doesn't trivially win without genuine task success.
7. Cost feasibility: standard tier runs repeatedly on one RTX 5090.
Until ALL pass: CANDIDATE, displayed separately. If it validates -> future "Overall Local Score",
NOT the existing Core Text (K+I) headline.

## Sequencing (from the execution plan)
Lane E = design/pilot, parallel to the gemma fix + v1, NOT a critical-path blocker. Target by end of
the 2-week window: AppWorld-lite scope + JSON protocol + verifier skeleton + a few smoke tasks +
the promotion-gate checklist. No leaderboard promotion, no composite inclusion yet.

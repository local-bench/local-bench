<task>
Build the AGENTIC axis for local-bench suite-v1 by vendoring the Berkeley Function-Calling Leaderboard
(BFCL) AST-based tool-call scorer (Apache-2.0) and building a frozen itemset from BFCL's
execution-FREE categories. This is the final axis of the launch core (knowledge / math /
instruction-following / agentic), so it must be faithful and clean.

Repo root: C:/Users/Michael/local-bench (cwd). Venv: cli/.venv (use ./.venv/Scripts/python.exe from
cli/). `datasets` is installed. Study existing scorers (cli/src/localbench/scorers/ifbench/, mcq.py) for
house style + the never-raise contract, but DO NOT modify them.

LESSON BAKED IN (do this in ONE pass, not three): include a LIVE reference-parity test vs the official
bfcl-eval AST checker FROM THE START, and keep the runtime scorer DEPENDENCY-FREE (any heavy reference
deps belong only in the dev/parity path, never imported by our scorer).
</task>

<context>
- Scope = BFCL's EXECUTION-FREE, AST-checkable categories ONLY: simple, multiple, parallel,
  parallel_multiple (single-turn function calling scored by matching the model's emitted call(s) against
  the expected possible-answer via AST — NO code execution, NO live API, NO judge model). EXCLUDE
  executable/* categories and multi-turn. You MAY include 'irrelevance' if you score it as "model
  correctly emitted NO function call".
- Confirm canonical sources + licenses before use and PIN revisions: the BFCL dataset (gorilla / BFCL)
  and the bfcl-eval package/repo (Apache-2.0).
- Our package cli/src/localbench/scorers/bfcl/ must expose BOTH:
    score_bfcl(prompt_item: Mapping, response_text: str) -> {"correct": bool, "extracted": str | None}
    build_bfcl_prompt(prompt_item: Mapping) -> str   # the function-calling prompt, faithful to
                                                      # bfcl-eval's PROMPTING format (tool schemas + the
                                                      # user query) so a plain chat model can answer
  score_bfcl must NEVER raise (return correct=False on malformed/unparseable output). The AST matcher
  must honor BFCL possible-answer semantics (multiple acceptable values per argument, optional args, type
  coercion) — MATCH bfcl-eval; do not invent a laxer or stricter rule.
- Item schema (suite/v1/bfcl.jsonl), self-contained per line, carrying everything the prompt builder and
  scorer need: e.g. {"id", "category", "question", "function" (tool schemas), "possible_answer"}. Use the
  fields bfcl-eval's AST checker consumes.
- The manager (Claude) owns suite.json, the dispatch (thin _suite.py / _scoring.py arms that call
  build_bfcl_prompt + score_bfcl), and templates. You produce the scorer package + itemset + builder +
  tests + datasheet ONLY.
</context>

<deliverables>
1. cli/src/localbench/scorers/bfcl/ — vendored AST checker + score_bfcl + build_bfcl_prompt, Apache
   NOTICE attribution, DEPENDENCY-FREE at runtime (stdlib only for the matcher/parser).
2. suite/v1/bfcl.jsonl — a frozen stratified subset (~300 items) spanning the AST categories above.
   Stable sequential ids ("bfcl-001" ...).
3. suite/build_v1_bfcl.py — reproducible (pin dataset + bfcl-eval revisions); byte-stable on rerun.
4. cli/tests/test_bfcl.py — unit tests (per category: a correct call + a wrong call) AND a LIVE PARITY
   test: install bfcl-eval (or import the pinned repo) into cli/.venv and run a sample of items through
   BOTH score_bfcl and bfcl-eval's AST checker, asserting identical correctness verdicts. If bfcl-eval
   genuinely cannot run here, say exactly why and stop (do not fake parity). Keep its heavy deps OUT of
   our scorer.
5. cli/tests/test_v1_bfcl_items.py — gate: items load, schema valid, ids unique, every item is
   AST-scorable (build_bfcl_prompt yields a non-empty prompt AND possible_answer is well-formed), and for
   each item the EXPECTED answer self-scores correct=True through score_bfcl. Fail loudly + name offenders.
</deliverables>

<action_safety>
Touch ONLY: cli/src/localbench/scorers/bfcl/**, suite/v1/bfcl.jsonl, suite/build_v1_bfcl.py,
cli/tests/test_bfcl.py, cli/tests/test_v1_bfcl_items.py, and (optionally) cli/pyproject.toml for a
bfcl-eval DEV/optional extra (parity only). Network for HF/pip/GitHub fetch only. Do NOT edit _scoring.py,
_suite.py, other scorers, suite/v0/, any suite.json, web/, or any existing test.
</action_safety>

<verification_loop>
From cli/: ./.venv/Scripts/python.exe -m pytest tests/test_bfcl.py tests/test_v1_bfcl_items.py -q must
pass with parity LIVE vs bfcl-eval, and the full suite ./.venv/Scripts/python.exe -m pytest -q must stay
green (currently 433). Report counts + the exact install commands run.
</verification_loop>

<completeness_contract>
Datasheet: dataset id + revision + license; bfcl-eval version + license; categories + item counts
included (and any excluded + why); self-score gate result (X/Y expected answers self-score correct); the
parity result (how many items compared live vs bfcl-eval, divergences + fixes); confirm the RUNTIME scorer
imports no heavy deps; 3 sample items; final pytest counts. Do NOT claim the axis is wired — wiring is
Claude's next step.
</completeness_contract>

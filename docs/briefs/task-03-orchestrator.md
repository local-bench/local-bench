<task>
Third slice for local-bench: the `localbench run` orchestrator that turns the existing
pieces (runner, scorers, suite v0 item sets) into a one-command benchmark run, plus two
scorer refinements. cli/ package and suite/v0/ item sets exist.

1. MCQ scorer revision (cli/src/localbench/scorers/mcq.py + tests):
   - Change the conflict rule for the explicit-marker pattern groups ("final answer",
     "answer is", \boxed, **X**): when multiple matches exist in a group, take the LAST
     match in document order instead of returning None — models self-correct mid-reasoning
     ("the answer is C... wait, no, the answer is D" must extract D).
   - Keep None-on-conflict ONLY for the low-confidence groups (standalone letter line,
     bare parenthesised letter in the tail).
   - Add/adjust tests: self-correction cases (same marker twice, different letters),
     marker-then-standalone-letter precedence, and keep all still-valid existing cases.
   - Add extract-aware API: score_mcq_detailed(text, gold, n_options) ->
     {"extracted": str|None, "correct": bool} (keep score_mcq as a thin wrapper).

2. Orchestrator (cli/src/localbench/orchestrate.py + cli/src/localbench/cli.py):
   - Console entrypoint `localbench` (console_scripts) and `python -m localbench`.
   - `localbench run --endpoint URL --model NAME [--bench all|mmlu_pro|ifeval|genmath]
     [--tier quick|standard] [--concurrency N] [--out PATH] [--api-key-env VAR]
     [--max-items N] [--suite-dir PATH] [--price-in USD_PER_MTOK] [--price-out USD_PER_MTOK]`
     Defaults: bench=all, tier=quick, concurrency=4, out=runs/<model>_<tier>_<timestamp>.json,
     suite-dir=auto-discover ../suite/v0 relative to repo OR --suite-dir explicit.
   - Loads suite/v0/suite.json (benches, item-set files, template files, per-bench decoding
     policy: temperature, max_tokens). genmath entries may not exist yet — handle a bench
     listed in suite.json whose item file is missing by skipping it with a warning.
   - Prompt rendering: mcq template fills {question} and {options} (lettered A./B./...);
     ifeval sends the dataset prompt verbatim; genmath (when present) fills {statement}
     into its template. All sent as a single user message.
   - Runs each bench through run_benchmark with the bench's decoding policy; --max-items N
     truncates each bench's item list (smoke runs).
   - Scoring: mcq via score_mcq_detailed; ifeval via the vendored checkers (strict);
     genmath via score_math (also record extracted). Per-item record: id, bench, response
     text, extracted (where applicable), correct, latency_seconds, usage, error.
   - Aggregates per bench: n, n_errors, n_extraction_failures, raw_accuracy,
     chance_corrected = (raw - baseline) / (1 - baseline) using the baseline from
     suite.json, clamped at >= 0. Composite: equal-weight mean of chance_corrected over
     benches that ran. If --price-in/--price-out given: estimated_cost_usd from summed
     usage.
   - Manifest collection (cli/src/localbench/manifest.py), best-effort per
     docs/manifest-schema.md: GET {endpoint}/models (OpenAI-compatible) for reported model
     id; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
     (tolerate absence); platform/OS; sampling params actually used; suite version +
     item-set hashes from suite/v0/itemsets.lock.json; lane field defaulting to
     "answer-only" with --lane override enum from the schema; canonical=false with
     missing_fields listed (P0 posture — file hashing comes later).
   - Final run JSON: {schema:"localbench-run-v0", manifest, benches:{...aggregates},
     composite, items:[...]} via write_json. Print a compact human summary table to stdout
     at the end (the ONE place printing is allowed): per bench raw/corrected/n/failures,
     composite, total tokens, wall time, tok/s, est cost if priced.

3. Tests (cli/tests/test_orchestrate.py + fixtures):
   - Tiny fixture suite under cli/tests/fixtures/suite_v0/ (3 mcq items, 2 ifeval items
     using simple checkable instructions, 2 genmath-style numeric items + suite.json +
     fake lock file) — orchestrator pointed at it with --suite-dir.
   - MockTransport endpoint returning canned responses (mix of right/wrong/extraction-
     garbage/one HTTP error) → assert per-bench aggregates, chance correction math,
     composite, extraction-failure counting, error counting, output JSON shape, and that
     --max-items truncates.
   - CLI smoke: `localbench run --help` exits 0; missing endpoint → clean error exit 2.
</task>

<action_safety>
Touch only cli/ (source + tests + pyproject for the console_scripts entry). Do NOT touch
suite/v0 real item sets, docs/, web/, repo root. No git commands. No real network in tests.
</action_safety>

<completeness_contract>
Done = full pytest suite green via cli/.venv (old + new tests, including revised MCQ
expectations); `cli/.venv/Scripts/localbench.exe run --help` (or python -m localbench run
--help) exits 0.
</completeness_contract>

<verification_loop>
Run pytest yourself; fix failures before finishing. Re-run the full suite, not just new
tests — the MCQ revision must not silently break task-01 cases that remain valid; where a
task-01 test contradicts the new conflict rule, update it deliberately and say so.
</verification_loop>

<missing_context_gating>No questions; decide and note.</missing_context_gating>

<compact_output_contract>
Final message: (1) files created/modified, (2) pytest line, (3) which task-01 tests you
changed for the new MCQ rule and why, (4) <=8 bullets decisions/deferred.
</compact_output_contract>

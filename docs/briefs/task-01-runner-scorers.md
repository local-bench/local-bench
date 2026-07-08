<task>
You are implementing the first slice of "local-bench" — a benchmark runner that drives
OpenAI-compatible LLM endpoints and scores responses. Work ONLY inside this repo
(C:\Users\Michael\local-bench). Current state: empty scaffold (cli/, suite/, docs/, web/).

Build a Python package under cli/:

1. Package layout: src layout — cli/pyproject.toml (setuptools or hatchling), package
   `localbench` at cli/src/localbench/. Python >=3.11. Runtime deps: httpx only.
   Dev deps: pytest. Keep it thin — no pydantic, no rich, no click for now.

2. localbench/runner.py — async driver for OpenAI-compatible chat completions:
   - Input: endpoint base_url, optional api_key, model name, list of items
     (each: id, messages, sampling params dict, max_tokens), concurrency int (default 4).
   - POST {base_url}/chat/completions, bounded by asyncio.Semaphore.
   - Capture per item: response text, finish_reason, usage (prompt_tokens,
     completion_tokens, total_tokens; tolerate missing usage), wall-clock latency,
     request started/finished timestamps, error (if any after retries).
   - Retries: network errors + HTTP 429/5xx, exponential backoff with jitter, max 3
     attempts; per-request timeout (default 300s — local reasoning models are slow).
   - Output: a run record — dict with run header (endpoint, model, params, started/finished,
     totals: items, errors, sum tokens, measured tok/s computed from completion tokens /
     active wall time) + per-item results list. Helper to write it as JSON to a path.
   - NO scoring inside the runner. NO printing inside the library (return data; a thin
     __main__ smoke entrypoint may print).

3. localbench/scorers/mcq.py:
   - extract_choice(text: str, n_options: int) -> str | None — extract the model's FINAL
     answer letter from free-form CoT text. Support up to 10 options (A-J).
   - Strategy: search from the END of the text backwards; prefer explicit markers:
     "answer is (C)", "Answer: C", "**C**", "\boxed{C}", "final answer: C", a trailing
     standalone letter line, "(C)" near the end; case-insensitive; reject letters that are
     just part of words; if multiple conflicting candidates at same priority, return None.
   - score_mcq(text, gold_letter, n_options) -> bool (None extraction = wrong).

4. localbench/scorers/math_numeric.py:
   - extract_final_number(text: str) -> str | None — prefer \boxed{...}, then
     "final answer"/"answer is" markers, then the last number in the text.
   - normalize: strip $, commas, trailing units/words, whitespace; support integers,
     decimals, simple fractions "a/b", negative numbers.
   - equivalent(a: str, b: str) -> bool using fractions.Fraction where possible; for
     floats, relative tolerance 1e-4. score_math(text, gold) -> bool.

5. Tests FIRST (TDD): cli/tests/test_mcq.py, test_math_numeric.py, test_runner.py.
   - Table-driven: >=25 MCQ extraction cases (trailing punctuation; CoT mentioning several
     letters then settling on one; "I considered C but the answer is D"; boxed; 10-option J;
     letter restated with option text; ambiguous -> None; empty/garbage -> None) and
     >=20 math cases (boxed, fractions 3/4 vs 0.75, commas 1,234, $ and units, negatives,
     scientific notation 3e8, last-number fallback, ambiguous garbage -> None).
   - Runner tests: mock the HTTP layer (httpx.MockTransport) — happy path, retry-then-
     success on 429, hard failure recorded as item error not exception, concurrency cap
     respected, usage-missing tolerated. No real network in tests.
</task>

<action_safety>
Only create/modify files under cli/. Do not touch suite/, web/, repo-root README.md,
.gitignore, or docs/ (except nothing — leave docs alone). No new top-level directories.
Do not run git commands; the manager commits.
</action_safety>

<completeness_contract>
Done means: a virtualenv at cli/.venv exists using a Python >=3.11 interpreter (use the
`py` launcher to find one, e.g. `py -3.14` or `py -3`; on this machine Python 3.14 may be
at %LOCALAPPDATA%\Programs\Python\Python314\python.exe or C:\Python314\python.exe — NEVER
bare `python`), `pip install -e cli/[dev]` (or equivalent) succeeded into that venv, and
`cli/.venv/Scripts/python -m pytest cli/tests -q` exits 0 with ALL tests passing.
</completeness_contract>

<verification_loop>
Run the test suite yourself after implementing; fix failures before finishing. If network
access for pip is unavailable in your sandbox, say so explicitly in your final message and
ensure the code+tests are complete so the manager can install and run them.
</verification_loop>

<missing_context_gating>
Do not ask questions. Make reasonable engineering choices and note them. Hard requirements
are only what the contracts above state.
</missing_context_gating>

<compact_output_contract>
Final message, in order: (1) file tree created under cli/, (2) pytest result line
(passed/failed counts) and the exact python used, (3) <=10 bullets of design decisions,
(4) anything deliberately deferred.
</compact_output_contract>

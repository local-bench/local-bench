<task>
Five independent correctness/security hardening fixes from the code review (branch
`refactor/architecture`). Each gets a focused test. Do NOT touch the web app or scoring estimand
(already done). Read each cited file before changing it.

FIX A — finding #4, langdetect dependency (cli/pyproject.toml + scorers/ifeval/_shared.py):
`langdetect` is used by IFEval language checks but is not a declared runtime dependency, so on a
normal install `detect_language` silently falls back to an ASCII heuristic and language-constrained
items mis-score. Make it explicit: add `langdetect` to the cli runtime dependencies AND make the
fallback non-silent — when langdetect is unavailable, the affected check must surface a benchmark
warning / be recorded as indeterminate rather than silently using the heuristic. Test: language check
behavior is correct when langdetect present; absence path is explicit (mock/monkeypatch import).

FIX B — finding #5, IFEval constrained-response exactness (scorers/ifeval/_checks_format.py:~47):
the constrained-response check accepts any allowed phrase as a SUBSTRING, so extra surrounding text or
multiple options wrongly pass. Match the OFFICIAL IFEval semantics: the response must equal exactly one
allowed option (compare the stripped response against the allowed set for exact membership; do not
substring-match). Test: "Answer: yes" with allowed {"Answer: yes","Answer: no"} passes; "Answer: yes and no"
or "...Answer: yes..." with trailing text fails per official behavior.

FIX C — finding #6 (SECURITY), redact provider error bodies (cli/src/localbench/_requests.py:~147):
HTTP error bodies are persisted verbatim into the stored result error, which can capture echoed API
keys / Authorization headers / proxy diagnostics and is unbounded. Store the status code plus a SHORT
(<=200 char) snippet with secrets redacted: replace anything matching `sk-[A-Za-z0-9_-]{8,}`,
`AIza[A-Za-z0-9_-]{10,}`, and `Bearer\s+[A-Za-z0-9._-]{8,}` with `***REDACTED***`. Never store the full
body. Test: an error body containing a fake `sk-ant-...` / `AIza...` / `Bearer ...` is redacted and truncated.

FIX D — finding #7, require an explicit private seed (suite/genmath_gen/build.py:~115):
the private sentinel build falls back to the PUBLIC deterministic seed when
`LOCALBENCH_GENMATH_PRIVATE_SEED` is unset, making "private" items reproducible if release tooling is
misconfigured. Require the secret seed for private builds: if a private build is requested and neither
the env var nor an explicit private-seed argument is provided, RAISE a clear error (do not fall back to
the public/default seed). The bundled default constant may be used ONLY when explicitly passed (e.g. by
tests). Public build is unchanged and must still produce byte-identical public files. Test: private
build without a seed raises; with an explicit/env seed it builds; public files are unchanged.

FIX E — finding #10, mcq final-answer conflict (cli/src/localbench/scorers/mcq.py:~12):
the "final answer"/"answer" marker patterns disable the distinct-letter conflict check, so
"Final answer: A or B" scores as A. Apply the conflict check to these marker patterns too: if a single
final-answer span yields MULTIPLE DISTINCT allowed letters, return None (ambiguous) rather than the last.
Keep legitimate single-letter extraction working ("Final answer: C" -> C; "The answer is (D)." -> D).
Test: "Final answer: A or B" -> None; "Final answer: C" -> C; existing extraction tests still pass.
</task>

<action_safety>
Touch ONLY: cli/pyproject.toml, cli/src/localbench/scorers/ifeval/_shared.py,
cli/src/localbench/scorers/ifeval/_checks_format.py, cli/src/localbench/_requests.py,
cli/src/localbench/scorers/mcq.py, suite/genmath_gen/build.py, and their test files under cli/tests/.
Do NOT touch the web app, _scoring.py, build_data.py, the runner/providers beyond _requests redaction,
or regenerate the committed suite item sets. No git commits. No network.
</action_safety>

<completeness_contract>
Done = full `cli/.venv/Scripts/python -m pytest cli/tests -q` green including the 5 new tests; the public
genmath files remain byte-identical (verify hashes unchanged); langdetect declared in pyproject; no
verbatim provider error bodies stored; private build refuses to use the public seed.
</completeness_contract>

<verification_loop>
Run the full suite. Rebuild the PUBLIC genmath set and confirm its sha256 is unchanged vs committed.
Confirm the redaction regex catches sk-/AIza/Bearer. Confirm "Final answer: A or B" now returns None.
Fix anything failing before finishing.
</verification_loop>

<missing_context_gating>No questions. If the official IFEval constrained-response set semantics are
ambiguous, prefer exact stripped-equality to the smallest reasonable allowed set and note it.</missing_context_gating>

<compact_output_contract>
Final: (1) files changed, (2) pytest line + public-genmath hash-unchanged confirmation, (3) one line per
fix A-E describing the change, (4) <=4 bullets on anything a reviewer should double-check (esp. IFEval
exactness vs official, and the redaction patterns).
</compact_output_contract>
